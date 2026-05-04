"""Order confirmation projections consumed by storefront templates."""

from __future__ import annotations

from shopman.shop.services.order_confirmation import (
    OrderConfirmationProjection,
    build_confirmation,
)


def build_order_confirmation(order, *, share_url: str) -> OrderConfirmationProjection:
    """Build the confirmation page projection for a just-placed Order."""
    return build_confirmation(order, share_url=share_url)


__all__ = ["OrderConfirmationProjection", "build_order_confirmation"]
