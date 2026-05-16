"""Canonical projection service for customer order confirmation pages."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.projections.types import OrderItemProjection

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrderConfirmationProjection:
    """Canonical confirmation projection independent from storefront templates."""

    order_ref: str
    items: tuple[OrderItemProjection, ...]
    total_display: str
    share_text: str
    eta: datetime | None


def build_confirmation(order, *, share_url: str) -> OrderConfirmationProjection:
    """Build confirmation data for a just-placed order."""
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

    eta = _eta(order)
    shop_name = _shop_name()

    return OrderConfirmationProjection(
        order_ref=order.ref,
        items=items,
        total_display=f"R$ {format_money(order.total_q)}",
        share_text=f"Fiz um pedido em {shop_name}! Acompanhe: {share_url}",
        eta=eta,
    )


def _eta(order) -> datetime | None:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        prep_minutes = getattr(shop, "prep_time_minutes", None) or 30
        return timezone.localtime(order.created_at) + timezone.timedelta(minutes=prep_minutes)
    except Exception:
        logger.debug("order_confirmation_eta_failed order=%s", order.ref, exc_info=True)
        return None


def _shop_name() -> str:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        return getattr(shop, "name", None) or "nossa loja"
    except Exception:
        logger.debug("order_confirmation_shop_name_failed", exc_info=True)
        return "nossa loja"


__all__ = ["OrderConfirmationProjection", "build_confirmation"]
