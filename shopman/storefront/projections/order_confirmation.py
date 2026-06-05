"""Order confirmation presentation — formats the data projection for templates.

Consumes ``shop.projections.order_confirmation`` (data) and produces the
display-ready shape the confirmation template renders: ``R$`` strings and the
WhatsApp share text. No policy, no Core.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from shopman.utils.monetary import format_money

from shopman.shop.projections.order_confirmation import build_confirmation
from shopman.shop.projections.types import OrderItemProjection


@dataclass(frozen=True)
class OrderConfirmationProjection:
    """Display-ready confirmation page projection."""

    order_ref: str
    items: tuple[OrderItemProjection, ...]
    total_display: str
    share_text: str
    eta: datetime | None


def build_order_confirmation(order, *, share_url: str) -> OrderConfirmationProjection:
    """Build the confirmation page projection for a just-placed Order."""
    data = build_confirmation(order)
    items = tuple(
        OrderItemProjection(
            sku=item.sku,
            name=item.name,
            qty=item.qty,
            unit_price_display=f"R$ {format_money(item.unit_price_q)}",
            total_display=f"R$ {format_money(item.line_total_q)}",
        )
        for item in data.items
    )
    return OrderConfirmationProjection(
        order_ref=data.order_ref,
        items=items,
        total_display=f"R$ {format_money(data.total_q)}",
        share_text=f"Fiz um pedido em {data.shop_name}! Acompanhe: {share_url}",
        eta=data.eta,
    )


__all__ = ["OrderConfirmationProjection", "build_order_confirmation"]
