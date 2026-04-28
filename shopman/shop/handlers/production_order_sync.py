"""Visual sync between orders and production work orders.

The link is intentionally contextual and denormalized: orders keep
``data["awaiting_wo_refs"]`` and work orders keep
``meta["serves_order_refs"]``. The production and order cores remain
unchanged; Backstage uses these refs to explain operational dependencies.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)

ACTIVE_ORDER_STATUSES = ("confirmed", "preparing", "ready")


def connect() -> None:
    """Wire order and production lifecycle receivers."""
    from shopman.craftsman.signals import production_changed
    from shopman.orderman.signals import order_changed

    order_changed.connect(
        link_order_to_work_orders,
        dispatch_uid="shopman.shop.handlers.production_order_sync.link_order_to_work_orders",
        weak=False,
    )
    production_changed.connect(
        link_work_order_to_orders,
        dispatch_uid="shopman.shop.handlers.production_order_sync.link_work_order_to_orders",
        weak=False,
    )
    logger.info("shopman.handlers: connected production/order sync receivers.")


def link_order_to_work_orders(sender=None, order=None, event_type: str = "", actor: str = "", **kwargs) -> None:
    """Attach a confirmed order to suitable planned/started work orders."""
    if order is None or order.status not in ACTIVE_ORDER_STATUSES:
        return
    if event_type and event_type not in {"created", "status_changed"}:
        return

    from shopman.craftsman.models import Recipe

    recipes_by_sku = {
        recipe.output_sku: recipe
        for recipe in Recipe.objects.filter(
            output_sku__in=_order_skus(order),
            is_active=True,
        )
    }
    if not recipes_by_sku:
        return

    changed = False
    for item in order.items.all():
        if item.sku not in recipes_by_sku:
            continue
        work_order = _candidate_work_order(item.sku, target_date=_target_date(order))
        if not work_order:
            continue
        changed = _append_order_work_order_link(order, work_order) or changed

    if changed:
        order.save(update_fields=["data", "updated_at"])


def link_work_order_to_orders(sender=None, action: str = "", work_order=None, **kwargs) -> None:
    """Attach or detach orders when a work order changes state."""
    if work_order is None:
        return

    if action == "voided":
        _unlink_voided_work_order(work_order)
        return

    if action not in {"planned", "adjusted", "started", "finished"}:
        return

    from shopman.orderman.models import Order

    orders = (
        Order.objects.filter(status__in=ACTIVE_ORDER_STATUSES, items__sku=work_order.output_sku)
        .distinct()
        .prefetch_related("items")
        .order_by("created_at")
    )
    for order in orders:
        if _target_date(order) > (work_order.target_date or date.today()):
            continue
        if _append_order_work_order_link(order, work_order):
            order.save(update_fields=["data", "updated_at"])


def order_requirement_for_work_order(work_order) -> Decimal:
    """Return the total ordered quantity for refs linked to ``work_order``."""
    from shopman.orderman.models import Order

    refs = tuple(dict.fromkeys((work_order.meta or {}).get("serves_order_refs") or ()))
    if not refs:
        return Decimal("0")
    total = Decimal("0")
    for order in Order.objects.filter(ref__in=refs).prefetch_related("items"):
        for item in order.items.all():
            if item.sku == work_order.output_sku:
                total += item.qty
    return total


def linked_order_refs(work_order) -> tuple[str, ...]:
    return tuple(dict.fromkeys((work_order.meta or {}).get("serves_order_refs") or ()))


def _append_order_work_order_link(order, work_order) -> bool:
    order_refs = list((order.data or {}).get("awaiting_wo_refs") or [])
    wo_refs = list((work_order.meta or {}).get("serves_order_refs") or [])
    changed = False

    if work_order.ref not in order_refs:
        order.data = {**(order.data or {}), "awaiting_wo_refs": [*order_refs, work_order.ref]}
        changed = True
    if order.ref not in wo_refs:
        work_order.meta = {**(work_order.meta or {}), "serves_order_refs": [*wo_refs, order.ref]}
        work_order.save(update_fields=["meta", "updated_at"])
        changed = True
    return changed


def _unlink_voided_work_order(work_order) -> None:
    from shopman.orderman.models import Order

    refs = linked_order_refs(work_order)
    if not refs:
        return
    with transaction.atomic():
        for order in Order.objects.select_for_update().filter(ref__in=refs):
            existing = list((order.data or {}).get("awaiting_wo_refs") or [])
            updated = [ref for ref in existing if ref != work_order.ref]
            if updated != existing:
                data = {**(order.data or {})}
                if updated:
                    data["awaiting_wo_refs"] = updated
                else:
                    data.pop("awaiting_wo_refs", None)
                order.data = data
                order.save(update_fields=["data", "updated_at"])
        meta = {**(work_order.meta or {})}
        meta.pop("serves_order_refs", None)
        work_order.meta = meta
        work_order.save(update_fields=["meta", "updated_at"])


def _candidate_work_order(sku: str, *, target_date: date):
    from shopman.craftsman.models import WorkOrder

    qs = WorkOrder.objects.filter(
        output_sku=sku,
        status__in=(WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED),
        target_date__lte=target_date,
    )
    strategy = _match_strategy()
    if strategy == "earliest_target":
        return qs.order_by("target_date", "created_at").first()
    if strategy == "manual":
        return None
    return qs.order_by("created_at").first()


def _match_strategy() -> str:
    try:
        from shopman.shop.models import Shop

        strategy = (Shop.load().defaults or {}).get("production_order_match") or "first_planned"
        if strategy in {"first_planned", "earliest_target", "manual"}:
            return strategy
    except Exception:
        logger.debug("production_order_sync.strategy_failed", exc_info=True)
    return "first_planned"


def _order_skus(order) -> tuple[str, ...]:
    return tuple({item.sku for item in order.items.all() if item.sku})


def _target_date(order) -> date:
    raw = (order.data or {}).get("target_date") or (order.data or {}).get("production_target_date")
    if raw:
        try:
            return date.fromisoformat(str(raw))
        except ValueError:
            pass
    return order.created_at.date() if order.created_at else date.today()
