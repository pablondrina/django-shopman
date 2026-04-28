"""Production alert handlers for operator surfaces."""

from __future__ import annotations

import logging
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from shopman.shop.adapters import alert as alert_adapter


LOW_YIELD_THRESHOLD = Decimal("0.80")
DEFAULT_STARTED_MINUTES = 240
logger = logging.getLogger(__name__)


def connect() -> None:
    """Connect production alert receivers to Craftsman lifecycle signals."""
    from shopman.craftsman.signals import production_changed

    production_changed.connect(
        on_production_changed,
        dispatch_uid="shopman.shop.handlers.production_alerts.on_production_changed",
        weak=False,
    )


def on_production_changed(sender, product_ref, date, action, work_order, **kwargs):
    """Create operator alerts for production lifecycle events."""
    if action == "finished":
        maybe_create_low_yield_alert(work_order)


def maybe_create_low_yield_alert(work_order) -> bool:
    """Create a low-yield alert when finished quantity is below threshold."""
    if work_order.finished is None:
        return False

    base_qty = work_order.started_qty or work_order.quantity
    if not base_qty:
        return False

    yield_rate = work_order.finished / base_qty
    if yield_rate >= LOW_YIELD_THRESHOLD:
        return False

    message = (
        f"Produção {work_order.ref} ({work_order.output_sku}) fechou com "
        f"yield de {int(yield_rate * 100)}%."
    )
    if _recent_exists("production_low_yield", work_order.ref):
        return False
    alert_adapter.create(
        "production_low_yield",
        "warning",
        message,
        order_ref=work_order.ref,
    )
    return True


def check_late_started_orders(*, selected_date=None) -> int:
    """Create alerts for started work orders beyond their target window."""
    from shopman.craftsman.models import WorkOrder

    qs = WorkOrder.objects.filter(status=WorkOrder.Status.STARTED).select_related("recipe")
    if selected_date is not None:
        qs = qs.filter(target_date=selected_date)

    created = 0
    now = timezone.now()
    for work_order in qs:
        started_at = work_order.started_at or work_order.created_at
        target_minutes = _target_minutes(work_order)
        if started_at > now - timedelta(minutes=target_minutes):
            continue
        if _recent_exists("production_late", work_order.ref):
            continue
        alert_adapter.create(
            "production_late",
            "warning",
            (
                f"Produção {work_order.ref} ({work_order.output_sku}) está há "
                f"{int((now - started_at).total_seconds() // 60)} min em andamento."
            ),
            order_ref=work_order.ref,
        )
        created += 1
    return created


def create_stock_short_alert(*, work_order_ref: str, output_sku: str, error: str) -> None:
    """Create an alert for a failed finish caused by stock/inventory shortage."""
    if _recent_exists("production_stock_short", work_order_ref):
        return
    alert_adapter.create(
        "production_stock_short",
        "error",
        f"Produção {work_order_ref} ({output_sku}) falhou por estoque insuficiente: {error}",
        order_ref=work_order_ref,
    )


def _target_minutes(work_order) -> int:
    try:
        raw = (work_order.recipe.meta or {}).get("max_started_minutes")
        if raw not in (None, ""):
            value = int(raw)
            if value > 0:
                return value
    except Exception:
        logger.debug("production_alerts.invalid_target_minutes work_order=%s", work_order.pk, exc_info=True)
    return DEFAULT_STARTED_MINUTES


def _recent_exists(alert_type: str, work_order_ref: str) -> bool:
    return alert_adapter.recent_exists(
        alert_type,
        timezone.now() - timedelta(hours=12),
        message_contains=work_order_ref,
    )
