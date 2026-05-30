"""
KDS (Kitchen Display System) dispatch service.

Bridge: KDS is reactive to the order lifecycle (unidirecional Order→KDS):
- dispatch()         — cria tickets quando o trabalho físico é liberado; o lifecycle grava PREPARING em seguida
- cancel_tickets()   — cancela tickets abertos quando Order é CANCELLED
- on_all_tickets_done() — transiciona Order para READY quando todos os tickets concluídos

Invariantes garantidos:
- dispatch() é idempotente: não cria duplicatas se já há tickets para o pedido
- cancel_tickets() é idempotente: retorna 0 sem erro se não há tickets abertos
- Tickets órfãos (Order cancelado mas tickets ainda abertos) não podem ocorrer se
  lifecycle on_cancelled chamar cancel_tickets() corretamente

Core: KDSInstance, KDSTicket (models), Recipe (craftsman), CollectionItem (offerman)
"""

from __future__ import annotations

import logging
from collections import defaultdict

from django.utils import timezone
from shopman.orderman.models import Order

from shopman.shop.services.order_helpers import get_fulfillment_type

logger = logging.getLogger(__name__)

OPEN_TICKET_STATUSES = {"pending", "in_progress"}


def dispatch(order) -> list:
    """
    Route an order's not-yet-fired lines to KDS, creating KDSTickets.

    Reconciliation at commit: a comanda may have fired courses progressively
    before commit, so dispatch fires only the remaining (unfired) lines. Delta
    is computed per ``line_id`` against the live ticket ledger, so a fresh order
    fires everything and an already-fired one fires nothing (idempotent).

    Returns list of created KDSTicket instances.

    SYNC — tickets must be ready for the KDS display.
    """
    lines = _order_to_lines(order)
    if not lines:
        return []
    tickets = fire_lines(session_key=order.session_key, lines=lines)
    if tickets:
        logger.info("kds.dispatch: %d tickets for order %s", len(tickets), order.ref)
    return tickets


def fire_lines(*, session_key: str, lines: list[dict]) -> list:
    """
    Route the not-yet-fired delta of ``lines`` to KDS instances.

    Source-agnostic: ``lines`` may come from a committed Order (commit
    reconciliation) or an open Session (progressive comanda fire). Each line is
    a dict ``{line_id, sku, name, qty, notes, meta}``.

    For each routable item:
    - active Recipe → type "prep"; otherwise "picking"
    - match to KDSInstance by type + collection overlap, preferring a
      collection-specific station over a generic catch-all

    Idempotent per ``line_id``: a line already on a live (non-cancelled) ticket
    is skipped; a cancelled line may re-fire (reprint). Returns created tickets.
    """
    from shopman.shop.adapters import get_adapter
    from shopman.shop.adapters import kds as kds_adapter

    already_fired = kds_adapter.fired_line_ids_for_session(session_key)
    pending = [
        ln for ln in lines
        if ln.get("line_id") and ln["line_id"] not in already_fired
    ]
    if not pending:
        return []

    # Get active KDS instances (exclude expedition — query-based)
    instances = kds_adapter.get_active_prep_instances()
    if not instances:
        return []

    catalog = get_adapter("catalog")
    routable_items = _build_routable_items(pending)
    skus = list({item["sku"] for item in routable_items})

    # Bulk-query primary collections: sku → collection_id
    sku_to_collection = catalog.bulk_sku_to_collection_id(skus)

    # Bulk-query recipes: set of SKUs that need prep
    production = get_adapter("production")
    prep_skus = production.get_prep_skus(skus) if production else set()

    # Build instance lookup: (type, collection_id) → [instance, ...]
    type_col_map = defaultdict(list)
    catchall_map = defaultdict(list)

    for inst in instances:
        col_ids = set(inst.collections.values_list("id", flat=True))
        if not col_ids:
            catchall_map[inst.type].append(inst)
        else:
            for col_id in col_ids:
                type_col_map[(inst.type, col_id)].append(inst)

    # Route each item. Bundles are expanded by _build_routable_items(), so
    # each component can land in the correct KDS station independently. The
    # component carries its parent line's line_id so dedup stays per-line.
    instance_items = defaultdict(list)

    for item in routable_items:
        sku = item["sku"]
        item_type = "prep" if sku in prep_skus else "picking"
        col_id = sku_to_collection.get(sku)

        matched = _match_instances(
            item_type=item_type,
            collection_id=col_id,
            type_col_map=type_col_map,
            catchall_map=catchall_map,
        )

        if not matched:
            logger.warning(
                "kds.fire_lines: no KDS instance for sku=%s type=%s col=%s parent=%s - skipped",
                sku, item_type, col_id, item.get("parent_sku") or "-",
            )
            continue

        item_dict = {
            "sku": sku,
            "name": item["name"],
            "qty": item["qty"],
            "notes": item["notes"],
            "checked": False,
            "line_id": item["line_id"],
        }

        for inst in matched:
            instance_items[inst.pk].append(item_dict)

    # Create KDSTickets
    tickets = []
    inst_by_pk = {inst.pk: inst for inst in instances}

    for inst_pk, items in instance_items.items():
        ticket = kds_adapter.create_ticket(session_key, inst_by_pk[inst_pk], items)
        tickets.append(ticket)

    return tickets


def fired_line_ids(session_key: str) -> set:
    """Line ids already on a live (non-cancelled) ticket for this session_key."""
    from shopman.shop.adapters import kds as kds_adapter

    return kds_adapter.fired_line_ids_for_session(session_key)


def unfire_lines(*, session_key: str, line_ids: list[str]) -> dict:
    """Cancel the kitchen fire for specific lines, freeing them to re-fire."""
    from shopman.shop.adapters import kds as kds_adapter

    return kds_adapter.unfire_session_lines(session_key, line_ids)


def _order_to_lines(order) -> list[dict]:
    """Normalize an Order's items to source-agnostic fire lines."""
    lines = []
    for item in order.items.all():
        meta = item.meta or {}
        lines.append({
            "line_id": item.line_id,
            "sku": item.sku,
            "name": item.name or item.sku,
            "qty": int(item.qty),
            "notes": meta.get("notes", ""),
            "meta": meta,
        })
    return lines


def _match_instances(
    *,
    item_type: str,
    collection_id: int | None,
    type_col_map: dict,
    catchall_map: dict,
) -> list:
    """Return KDS instances for one routable item.

    Recipe tells whether an item is batch production. Collection tells which
    real workstation owns the item. A collection-specific station must win
    over a generic catch-all, otherwise drinks and made-to-order items without
    a Recipe end up in the "Encomendas" bucket.
    """
    if collection_id:
        exact = type_col_map.get((item_type, collection_id), [])
        if exact:
            return exact

        fallback_type = "prep" if item_type == "picking" else "picking"
        collection_specific = type_col_map.get((fallback_type, collection_id), [])
        if collection_specific:
            return collection_specific

    catchall = catchall_map.get(item_type, [])
    if catchall:
        return catchall

    if item_type == "prep":
        return catchall_map.get("picking", [])
    return []


def _build_routable_items(lines: list[dict]) -> list[dict]:
    """Expand normalized fire lines to concrete SKUs for KDS routing.

    ``lines``: ``[{line_id, sku, name, qty, notes, meta}]`` — source-agnostic
    (Order or open Session). Bundles expand to their components; each component
    inherits the parent line's ``line_id`` so the fire-ledger stays per-line.
    """
    from shopman.offerman.models import ProductComponent

    skus = [ln["sku"] for ln in lines]
    bundle_components = defaultdict(list)
    for pc in (
        ProductComponent.objects
        .filter(parent__sku__in=skus)
        .select_related("component")
    ):
        bundle_components[pc.parent.sku].append((
            pc.component.sku,
            pc.component.name,
            pc.qty,
        ))

    routable_items = []
    for ln in lines:
        meta = ln.get("meta") or {}
        if meta.get("non_production") or meta.get("type") == "delivery_fee":
            continue
        notes = ln.get("notes") or meta.get("notes", "")
        line_id = ln.get("line_id", "")
        qty = int(ln["qty"])
        name = ln.get("name") or ln["sku"]
        components = bundle_components.get(ln["sku"], [])
        if components:
            for comp_sku, comp_name, comp_qty in components:
                routable_items.append({
                    "sku": comp_sku,
                    "name": f"{comp_name} ({name})",
                    "qty": qty * comp_qty,
                    "notes": notes,
                    "parent_sku": ln["sku"],
                    "line_id": line_id,
                })
            continue

        routable_items.append({
            "sku": ln["sku"],
            "name": name,
            "qty": qty,
            "notes": notes,
            "parent_sku": None,
            "line_id": line_id,
        })
    return routable_items


def cancel_tickets(order) -> int:
    """
    Cancel all open KDS tickets for this order.

    Called by lifecycle on_cancelled to prevent tickets from becoming orphans
    (kitchen producing items for an already-cancelled order).

    Idempotent: safe to call even if there are no open tickets.

    Returns count of cancelled tickets.

    SYNC — tickets must be cancelled immediately when order is cancelled.
    """
    from shopman.shop.adapters import kds as kds_adapter

    count = kds_adapter.cancel_open_tickets(order)
    if count:
        logger.info("kds.cancel_tickets: cancelled %d tickets for order=%s", count, order.ref)
    return count


def on_all_tickets_done(order, *, actor: str = "kds.all_done") -> bool:
    """
    Check if all KDS tickets are done and transition order to READY.

    Called when a ticket is marked as done. If all tickets for the order
    are now done, transitions the order to READY status.

    Returns True if transitioned, False otherwise.

    SYNC — checks and transitions immediately.
    """
    from shopman.shop.adapters import kds as kds_adapter

    tickets = kds_adapter.get_tickets(order)
    if not tickets.exists():
        return False

    all_done = not tickets.exclude(status="done").exists()
    if not all_done:
        return False

    if order.status == Order.Status.READY:
        return False
    if order.status == Order.Status.CONFIRMED:
        if not _ensure_order_preparing_for_work(order, actor=actor):
            return False
    if not order.can_transition_to(Order.Status.READY):
        return False

    order.transition_status(Order.Status.READY, actor=actor)
    logger.info("kds.on_all_tickets_done: order %s → READY", order.ref)
    return True


def _ticket_order(ticket):
    """Resolve a ticket's ``session_key`` to its committed Order, if any.

    A ticket fired from an open comanda (pre-commit) has no Order yet — the
    same ``session_key`` only resolves to an Order after ``commit``. The
    done-loop (advance to PREPARING / READY) is a no-op until then: kitchen
    progress on an open comanda does not move an order that does not exist.
    """
    return Order.objects.filter(session_key=ticket.session_key).order_by("-id").first()


def toggle_ticket_item(ticket, *, index: int, actor: str) -> bool:
    """Toggle a KDS ticket item and start preparation when work begins."""
    if ticket.status not in OPEN_TICKET_STATUSES:
        return False
    if not 0 <= index < len(ticket.items):
        return False

    ticket.items[index]["checked"] = not ticket.items[index].get("checked", False)

    if ticket.status == "pending" and any(it.get("checked") for it in ticket.items):
        ticket.status = "in_progress"

    ticket.save(update_fields=["items", "status"])

    order = _ticket_order(ticket)
    if order is not None:
        _ensure_order_preparing_for_work(order, actor=actor)
    return True


def complete_ticket(ticket, *, actor: str) -> bool:
    """Mark a KDS ticket done and move the order to ready when all tickets finish."""
    if ticket.status not in OPEN_TICKET_STATUSES:
        return False
    order = _ticket_order(ticket)
    if order is not None and not _ensure_order_preparing_for_work(order, actor=actor):
        return False
    for item in ticket.items:
        item["checked"] = True
    ticket.status = "done"
    ticket.completed_at = timezone.now()
    ticket.save(update_fields=["items", "status", "completed_at"])

    logger.info("kds_done ticket=%d session=%s", ticket.pk, ticket.session_key)
    if order is None:
        return False
    return on_all_tickets_done(order, actor=actor)


def expedition_action(order, *, action: str, actor: str) -> str:
    """Apply an expedition action and return the new order status."""
    is_delivery = get_fulfillment_type(order) == "delivery"
    if action == "dispatch" and not is_delivery:
        raise ValueError("Pedido de retirada não pode ser despachado")
    if action == "complete" and order.status == Order.Status.READY and is_delivery:
        raise ValueError("Pedido de delivery precisa ser despachado antes de concluir")

    transitions = {
        "dispatch": Order.Status.DISPATCHED,
        "complete": Order.Status.COMPLETED,
    }
    next_status = transitions.get(action)
    if not next_status or not order.can_transition_to(next_status):
        raise ValueError("Ação inválida")
    order.transition_status(next_status, actor=actor)
    logger.info("kds_expedition %s order=%s", action, order.ref)
    return next_status


def expedition_action_by_order_id(order_id: int, *, action: str, actor: str) -> str:
    """Load an order and apply an expedition action."""
    order = Order.objects.filter(pk=order_id).first()
    if order is None:
        raise ValueError("Pedido não encontrado")
    return expedition_action(order, action=action, actor=actor)


def _payment_allows_physical_work(order) -> bool:
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return True
    from shopman.shop.services import payment as payment_service

    return payment_service.has_sufficient_captured_payment(order) is True


def _ensure_order_preparing_for_work(order, *, actor: str) -> bool:
    if order.status == Order.Status.PREPARING:
        return True
    if order.status != Order.Status.CONFIRMED:
        return False
    if not order.can_transition_to(Order.Status.PREPARING):
        return False
    if not _payment_allows_physical_work(order):
        return False
    order.transition_status(Order.Status.PREPARING, actor=actor)
    return True
