"""OrderConfirmationProjection — read model for the post-checkout confirmation page."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from shopman.utils.monetary import format_money
from shopman.shop.projections.types import OrderItemProjection

if TYPE_CHECKING:
    from shopman.orderman.models import Order


@dataclass(frozen=True)
class OrderConfirmationProjection:
    """Read model for the order confirmation page."""

    order_ref: str
    items: tuple[OrderItemProjection, ...]
    total_display: str
    share_text: str
    eta: datetime | None  # rendered via {% human_eta confirmation.eta %} in template


def build_order_confirmation(order: Order, *, share_url: str) -> OrderConfirmationProjection:
    """Build the confirmation page projection for a just-placed Order."""
    items = tuple(
        OrderItemProjection(
            sku=item.sku,
            name=item.name or item.sku,
            qty=int(item.qty),
            unit_price_display=f"R$ {format_money(item.unit_price_q)}",
            total_display=f"R$ {format_money(item.line_total_q)}",
        )
        for item in order.items.all()
    )

    eta: datetime | None = None
    try:
        from django.utils import timezone
        from shopman.shop.models import Shop

        shop = Shop.load()
        prep_minutes = getattr(shop, "prep_time_minutes", None) or 30
        eta = timezone.localtime(order.created_at) + timezone.timedelta(minutes=prep_minutes)
    except Exception:
        pass

    shop_name = "nossa loja"
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        shop_name = getattr(shop, "name", None) or shop_name
    except Exception:
        pass

    return OrderConfirmationProjection(
        order_ref=order.ref,
        items=items,
        total_display=f"R$ {format_money(order.total_q)}",
        share_text=f"Fiz um pedido em {shop_name}! Acompanhe: {share_url}",
        eta=eta,
    )


__all__ = ["OrderConfirmationProjection", "build_order_confirmation"]
