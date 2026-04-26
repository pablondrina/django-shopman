"""Customer-facing order reads and commands.

Storefront and API surfaces should use this module instead of importing
Orderman, Guestman, or Offerman models directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from django.shortcuts import get_object_or_404
from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.projections.types import ORDER_STATUS_COLORS, ORDER_STATUS_LABELS_PT
from shopman.shop.services import payment as payment_service

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = frozenset({"new", "confirmed", "preparing", "ready", "dispatched"})
CANCELLABLE_STATUSES = frozenset({"new", "confirmed"})
DEFAULT_CHANNEL_REF = "web"


@dataclass(frozen=True)
class OrderHistorySummary:
    """Canonical compact order read model for customer history surfaces."""

    ref: str
    created_at: Any
    total_q: int
    status: str
    status_label: str
    status_color: str
    item_count: int


def get_order(ref: str):
    """Return an order by ref or raise Http404."""
    from shopman.orderman.models import Order

    return get_object_or_404(Order, ref=ref)


def find_order(ref: str):
    """Return an order by ref, or None when it does not exist."""
    from shopman.orderman.models import Order

    return Order.objects.filter(ref=ref).first()


def active_order_count_for_phone(phone: str) -> int:
    """Count active orders for the customer phone used by account badges."""
    from shopman.orderman.models import Order

    return Order.objects.filter(
        handle_type="phone",
        handle_ref=phone,
        status__in=ACTIVE_STATUSES,
    ).count()


def history_summaries_for_phone(
    phone: str,
    *,
    filter_param: str = "todos",
    limit: int = 50,
) -> tuple[OrderHistorySummary, ...]:
    """Return canonical order summaries for a phone, degrading to an empty tuple."""
    try:
        from shopman.orderman.models import Order

        qs = Order.objects.filter(
            handle_type="phone",
            handle_ref=phone,
        ).order_by("-created_at")

        if filter_param == "ativos":
            qs = qs.filter(status__in=ACTIVE_STATUSES)
        elif filter_param == "anteriores":
            qs = qs.exclude(status__in=ACTIVE_STATUSES)

        return tuple(
            OrderHistorySummary(
                ref=order.ref,
                created_at=order.created_at,
                total_q=order.total_q,
                status=order.status,
                status_label=ORDER_STATUS_LABELS_PT.get(order.status, order.status),
                status_color=ORDER_STATUS_COLORS.get(
                    order.status,
                    "bg-surface-alt text-on-surface/60 border border-outline",
                ),
                item_count=order.items.count(),
            )
            for order in qs[:limit]
        )
    except Exception:
        logger.warning("customer_order_history_failed phone=%s", phone, exc_info=True)
        return ()


def history_summaries_for_customer_ref(
    customer_ref: str,
    *,
    limit: int = 10,
) -> tuple[OrderHistorySummary, ...]:
    """Return canonical order summaries for a customer ref."""
    try:
        from shopman.orderman.services import CustomerOrderHistoryService

        records = CustomerOrderHistoryService.list_customer_orders(customer_ref, limit=limit)
        return tuple(
            OrderHistorySummary(
                ref=r.order_ref,
                created_at=r.ordered_at,
                total_q=r.total_q,
                status=r.status,
                status_label=ORDER_STATUS_LABELS_PT.get(r.status, r.status),
                status_color=ORDER_STATUS_COLORS.get(
                    r.status,
                    "bg-surface-alt text-on-surface/60 border border-outline",
                ),
                item_count=r.items_count,
            )
            for r in records
        )
    except Exception:
        logger.debug("customer_order_history_by_ref_failed customer=%s", customer_ref, exc_info=True)
        return ()


def order_history_for_phone(phone: str, *, limit: int = 20) -> list[dict]:
    """Return API-ready customer order history for the authenticated account API."""
    return [
        {
            "ref": order.ref,
            "created_at": order.created_at,
            "total_display": f"R$ {format_money(order.total_q)}",
            "status": order.status,
            "status_label": order.status_label,
        }
        for order in history_summaries_for_phone(phone, limit=limit)
    ]


def last_reorder_context(*, customer_uuid, min_days: int) -> tuple[str | None, list[dict]]:
    """Return the last old-enough order ref and sealed snapshot items for reorder."""
    try:
        from shopman.guestman.services import customer as customer_service

        customer = customer_service.get_by_uuid(str(customer_uuid))
    except Exception:
        logger.warning("reorder_customer_lookup_failed customer_uuid=%s", customer_uuid, exc_info=True)
        return None, []

    if customer is None:
        logger.debug("reorder_customer_not_found customer_uuid=%s", customer_uuid)
        return None, []

    try:
        from shopman.orderman.models import Order

        last = (
            Order.objects.filter(data__customer_ref=customer.ref)
            .order_by("-created_at")
            .values("ref", "snapshot", "created_at")
            .first()
        )
    except Exception:
        logger.warning("reorder_order_lookup_failed customer_ref=%s", customer.ref, exc_info=True)
        return None, []

    if not last:
        logger.debug("reorder_no_previous_order customer_ref=%s", customer.ref)
        return None, []

    days_since = (timezone.now() - last["created_at"]).days
    if days_since <= min_days:
        logger.debug(
            "reorder_previous_order_too_recent order_ref=%s days_since=%s min_days=%s",
            last["ref"],
            days_since,
            min_days,
        )
        return None, []

    snapshot = last.get("snapshot") or {}
    return last["ref"], snapshot.get("items") or []


def get_payment_status(order) -> str | None:
    """Return the canonical payment status for an order."""
    return payment_service.get_payment_status(order)


def mock_confirm_payment(order) -> bool:
    """Drive the local mock payment confirmation flow."""
    return payment_service.mock_confirm(order)


def is_cancelled(order) -> bool:
    return order.status == "cancelled"


def can_cancel(order) -> bool:
    return order.status in CANCELLABLE_STATUSES


def cancel(order) -> None:
    from shopman.shop.services.cancellation import cancel as cancel_order

    cancel_order(order, reason="customer_requested", actor="customer.self_cancel")


def should_skip_confirmation(order) -> bool:
    """True when the channel auto-confirms and confirmation page should redirect."""
    if not order.channel_ref:
        return False

    try:
        from shopman.shop.config import ChannelConfig

        cfg = ChannelConfig.for_channel(order.channel_ref).confirmation
        return cfg.mode == "auto_confirm"
    except Exception:
        logger.warning("confirmation_config_lookup_failed order=%s", order.ref, exc_info=True)
        return False


def add_reorder_items(
    request,
    order,
    *,
    cart_service=None,
    channel_ref: str = DEFAULT_CHANNEL_REF,
) -> list[str]:
    """Add previous order items to the cart and return display names skipped."""
    from shopman.shop.services.cart import CartUnavailableError

    if cart_service is None:
        msg = "cart_service is required for customer reorder commands"
        raise ValueError(msg)

    skipped: list[str] = []

    for item in order.items.all():
        product = _sellable_product(item.sku)
        if product is None:
            skipped.append(item.sku)
            continue

        price_q = _price_q(product, channel_ref=channel_ref)
        try:
            cart_service.add_item(
                request,
                sku=item.sku,
                qty=int(item.qty),
                unit_price_q=price_q,
                is_d1=False,
            )
        except CartUnavailableError:
            skipped.append(product.name or item.sku)
        except Exception:
            logger.warning("reorder_add_item_failed order=%s sku=%s", order.ref, item.sku, exc_info=True)
            skipped.append(product.name or item.sku)

    return skipped


def _sellable_product(sku: str):
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku, is_published=True).first()
    if product and product.is_sellable:
        return product
    return None


def _price_q(product, *, channel_ref: str) -> int:
    from shopman.offerman.models import ListingItem

    item = (
        ListingItem.objects.filter(
            listing__ref=channel_ref,
            listing__is_active=True,
            product=product,
            is_published=True,
        )
        .order_by("-min_qty")
        .first()
    )
    if item:
        return item.price_q
    return product.base_price_q or 0


__all__ = [
    "ACTIVE_STATUSES",
    "OrderHistorySummary",
    "active_order_count_for_phone",
    "add_reorder_items",
    "can_cancel",
    "cancel",
    "find_order",
    "get_order",
    "get_payment_status",
    "history_summaries_for_phone",
    "history_summaries_for_customer_ref",
    "is_cancelled",
    "last_reorder_context",
    "mock_confirm_payment",
    "order_history_for_phone",
    "should_skip_confirmation",
]
