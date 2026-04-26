"""Storefront order read and customer-facing order command service."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils import timezone

from shopman.shop.services import payment as payment_svc

ACTIVE_STATUSES = frozenset({"new", "confirmed", "preparing", "ready", "dispatched"})
_CANCELLABLE_STATUSES = frozenset({"new", "confirmed"})


def get_order(ref: str):
    from shopman.orderman.models import Order

    return get_object_or_404(Order, ref=ref)


def active_order_count_for_phone(phone: str) -> int:
    from shopman.orderman.models import Order

    return Order.objects.filter(
        handle_type="phone",
        handle_ref=phone,
        status__in=ACTIVE_STATUSES,
    ).count()


def order_history_for_phone(phone: str, *, limit: int = 20) -> list[dict]:
    from shopman.orderman.models import Order
    from shopman.utils.monetary import format_money

    from shopman.shop.projections.types import ORDER_STATUS_LABELS_PT

    orders = Order.objects.filter(
        handle_type="phone",
        handle_ref=phone,
    ).order_by("-created_at")[:limit]

    return [
        {
            "ref": order.ref,
            "created_at": order.created_at,
            "total_display": f"R$ {format_money(order.total_q)}",
            "status": order.status,
            "status_label": ORDER_STATUS_LABELS_PT.get(order.status, order.status),
        }
        for order in orders
    ]


def find_order(ref: str):
    from shopman.orderman.models import Order

    return Order.objects.filter(ref=ref).first()


def last_reorder_context(*, customer_uuid, min_days: int) -> tuple[str | None, list[dict]]:
    """Return the last old-enough order ref and sealed snapshot items for reorder."""
    from shopman.guestman.services import customer as customer_service
    from shopman.orderman.models import Order

    customer = customer_service.get_by_uuid(str(customer_uuid))
    if customer is None:
        return None, []

    last = (
        Order.objects.filter(data__customer_ref=customer.ref)
        .order_by("-created_at")
        .values("ref", "snapshot", "created_at")
        .first()
    )
    if not last:
        return None, []

    days_since = (timezone.now() - last["created_at"]).days
    if days_since <= min_days:
        return None, []

    return last["ref"], last["snapshot"].get("items") or []


def payment_status(order) -> str:
    return payment_svc.get_payment_status(order)


def mock_confirm_payment(order) -> None:
    payment_svc.mock_confirm(order)


def is_cancelled(order) -> bool:
    return order.status == "cancelled"


def can_cancel(order) -> bool:
    return order.status in _CANCELLABLE_STATUSES


def cancel(order) -> None:
    from shopman.shop.services.cancellation import cancel as cancel_order

    cancel_order(order, reason="customer_requested", actor="customer.self_cancel")


def should_skip_confirmation(order) -> bool:
    if not order.channel_ref:
        return False

    from shopman.shop.config import ChannelConfig

    cfg = ChannelConfig.for_channel(order.channel_ref).confirmation
    return cfg.mode == "auto_confirm"


def add_reorder_items(request, order, *, cart_service=None) -> list[str]:
    from shopman.offerman.models import Product

    from shopman.shop.services.cart import CartUnavailableError
    from shopman.storefront.cart import CartService
    from shopman.storefront.services.product_cards import get_price_q, line_item_is_d1

    cart_service = cart_service or CartService
    skipped: list[str] = []
    for item in order.items.all():
        product = Product.objects.filter(sku=item.sku, is_published=True).first()
        if product and product.is_sellable:
            price_q = get_price_q(product)
            if price_q is None:
                price_q = 0
            try:
                cart_service.add_item(
                    request,
                    sku=item.sku,
                    qty=int(item.qty),
                    unit_price_q=price_q,
                    is_d1=line_item_is_d1(product),
                )
            except CartUnavailableError:
                skipped.append(product.name or item.sku)
        else:
            name = product.name if product else item.sku
            skipped.append(name)
    return skipped
