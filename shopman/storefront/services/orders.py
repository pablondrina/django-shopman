"""Storefront order read and customer-facing order command service."""

from __future__ import annotations

from shopman.shop.services import customer_orders


def get_order(ref: str):
    return customer_orders.get_order(ref)


def active_order_count_for_phone(phone: str) -> int:
    return customer_orders.active_order_count_for_phone(phone)


def order_history_for_phone(phone: str, *, limit: int = 20) -> list[dict]:
    return customer_orders.order_history_for_phone(phone, limit=limit)


def find_order(ref: str):
    return customer_orders.find_order(ref)


def last_reorder_context(*, customer_uuid, min_days: int) -> tuple[str | None, list[dict]]:
    """Return the last old-enough order ref and sealed snapshot items for reorder."""
    return customer_orders.last_reorder_context(customer_uuid=customer_uuid, min_days=min_days)


def payment_status(order) -> str:
    return customer_orders.get_payment_status(order)


def mock_confirm_payment(order) -> None:
    customer_orders.mock_confirm_payment(order)


def is_cancelled(order) -> bool:
    return customer_orders.is_cancelled(order)


def can_cancel(order) -> bool:
    return customer_orders.can_cancel(order)


def cancel(order) -> None:
    customer_orders.cancel(order)


def should_skip_confirmation(order) -> bool:
    return customer_orders.should_skip_confirmation(order)


def add_reorder_items(request, order, *, cart_service=None) -> list[str]:
    if cart_service is None:
        from shopman.storefront.cart import CartService

        cart_service = CartService
    return customer_orders.add_reorder_items(request, order, cart_service=cart_service)
