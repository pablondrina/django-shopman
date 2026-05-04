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


def dispatch(order) -> list:
    """
    Route order items to KDS instances, creating KDSTickets.

    For each OrderItem:
    - If item's product has an active Recipe → type = "prep"
    - Otherwise → type = "picking"
    - Match to KDSInstance by type + collection overlap
    - If no exact type match exists, prefer a collection-specific station
      before falling back to a generic catch-all
    - Fallback: instances with no collections (catch-all)

    Idempotent: skips if tickets already exist for this order.

    Returns list of created KDSTicket instances.

    SYNC — tickets must be ready for the KDS display.
    """
    from shopman.shop.adapters import get_adapter
    from shopman.shop.adapters import kds as kds_adapter

    # Idempotent check
    if kds_adapter.ticket_exists_for_order(order):
        return []

    # Get active KDS instances (exclude expedition — query-based)
    instances = kds_adapter.get_active_prep_instances()
    if not instances:
        return []

    order_items = list(order.items.all())
    if not order_items:
        return []

    catalog = get_adapter("catalog")
    routable_items = _build_routable_items(order_items)
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
    # each component can land in the correct KDS station independently.
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
                "kds.dispatch: no KDS instance for sku=%s type=%s col=%s parent=%s - skipped",
                sku, item_type, col_id, item.get("parent_sku") or "-",
            )
            continue

        item_dict = {
            "sku": sku,
            "name": item["name"],
            "qty": item["qty"],
            "notes": item["notes"],
            "checked": False,
        }

        for inst in matched:
            instance_items[inst.pk].append(item_dict)

    # Create KDSTickets
    tickets = []
    inst_by_pk = {inst.pk: inst for inst in instances}

    for inst_pk, items in instance_items.items():
        ticket = kds_adapter.create_ticket(order, inst_by_pk[inst_pk], items)
        tickets.append(ticket)

    logger.info("kds.dispatch: %d tickets for order %s", len(tickets), order.ref)
    return tickets


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


def _build_routable_items(order_items) -> list[dict]:
    """Return order items expanded to concrete SKUs for KDS routing."""
    from shopman.offerman.models import ProductComponent

    skus = [item.sku for item in order_items]
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
    for item in order_items:
        notes = item.meta.get("notes", "") if item.meta else ""
        components = bundle_components.get(item.sku, [])
        if components:
            for comp_sku, comp_name, comp_qty in components:
                routable_items.append({
                    "sku": comp_sku,
                    "name": f"{comp_name} ({item.name or item.sku})",
                    "qty": int(item.qty * comp_qty),
                    "notes": notes,
                    "parent_sku": item.sku,
                })
            continue

        routable_items.append({
            "sku": item.sku,
            "name": item.name or item.sku,
            "qty": int(item.qty),
            "notes": notes,
            "parent_sku": None,
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


def toggle_ticket_item(ticket, *, index: int, actor: str) -> bool:
    """Toggle a KDS ticket item and start preparation when work begins."""
    if not 0 <= index < len(ticket.items):
        return False

    ticket.items[index]["checked"] = not ticket.items[index].get("checked", False)

    if ticket.status == "pending" and any(it.get("checked") for it in ticket.items):
        ticket.status = "in_progress"

    ticket.save(update_fields=["items", "status"])

    _ensure_order_preparing_for_work(ticket.order, actor=actor)
    return True


def complete_ticket(ticket, *, actor: str) -> bool:
    """Mark a KDS ticket done and move the order to ready when all tickets finish."""
    _ensure_order_preparing_for_work(ticket.order, actor=actor)
    for item in ticket.items:
        item["checked"] = True
    ticket.status = "done"
    ticket.completed_at = timezone.now()
    ticket.save(update_fields=["items", "status", "completed_at"])

    logger.info("kds_done ticket=%d order=%s", ticket.pk, ticket.order.ref)
    return on_all_tickets_done(ticket.order, actor=actor)


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
