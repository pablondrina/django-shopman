"""
KDS (Kitchen Display System) dispatch service.

Bridge: KDS is reactive to Order.status (unidirecional Order→KDS):
- dispatch()         — cria tickets quando Order entra em PREPARING
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

logger = logging.getLogger(__name__)


def dispatch(order) -> list:
    """
    Route order items to KDS instances, creating KDSTickets.

    For each OrderItem:
    - If item's product has an active Recipe → type = "prep"
    - Otherwise → type = "picking"
    - Match to KDSInstance by type + collection overlap
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

    skus = [item.sku for item in order_items]

    # Bulk-query primary collections: sku → collection_id
    catalog = get_adapter("catalog")
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

    # Route each item
    instance_items = defaultdict(list)

    for item in order_items:
        item_type = "prep" if item.sku in prep_skus else "picking"
        col_id = sku_to_collection.get(item.sku)

        matched = []
        if col_id:
            matched = type_col_map.get((item_type, col_id), [])
        if not matched:
            matched = catchall_map.get(item_type, [])
        if not matched and item_type == "prep":
            matched = catchall_map.get("picking", [])

        if not matched:
            logger.warning(
                "kds.dispatch: no KDS instance for sku=%s type=%s col=%s — skipped",
                item.sku, item_type, col_id,
            )
            continue

        item_dict = {
            "sku": item.sku,
            "name": item.name or item.sku,
            "qty": int(item.qty),
            "notes": item.meta.get("notes", "") if item.meta else "",
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

    order = ticket.order
    if order.status == Order.Status.CONFIRMED and order.can_transition_to(Order.Status.PREPARING):
        order.transition_status(Order.Status.PREPARING, actor=actor)
    return True


def complete_ticket(ticket, *, actor: str) -> bool:
    """Mark a KDS ticket done and move the order to ready when all tickets finish."""
    for item in ticket.items:
        item["checked"] = True
    ticket.status = "done"
    ticket.completed_at = timezone.now()
    ticket.save(update_fields=["items", "status", "completed_at"])

    logger.info("kds_done ticket=%d order=%s", ticket.pk, ticket.order.ref)
    return on_all_tickets_done(ticket.order, actor=actor)


def expedition_action(order, *, action: str, actor: str) -> str:
    """Apply an expedition action and return the new order status."""
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
