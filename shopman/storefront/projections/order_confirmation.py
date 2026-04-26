"""OrderConfirmationProjection — read model for the post-checkout confirmation page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shopman.shop.projections.types import OrderItemProjection
from shopman.shop.services import order_confirmation


@dataclass(frozen=True)
class OrderConfirmationProjection:
    """Read model for the order confirmation page."""

    order_ref: str
    items: tuple[OrderItemProjection, ...]
    total_display: str
    share_text: str
    eta: datetime | None  # rendered via {% human_eta confirmation.eta %} in template


def build_order_confirmation(order, *, share_url: str) -> OrderConfirmationProjection:
    """Build the confirmation page projection for a just-placed Order."""
    read_model = order_confirmation.build_confirmation(order, share_url=share_url)
    return OrderConfirmationProjection(
        order_ref=read_model.order_ref,
        items=read_model.items,
        total_display=read_model.total_display,
        share_text=read_model.share_text,
        eta=read_model.eta,
    )


__all__ = ["OrderConfirmationProjection", "build_order_confirmation"]
