"""Order confirmation read-side projection — semantic data, surface-agnostic.

Drained out of ``services/order_confirmation`` (which mixed ``format_money``
and share copy into the orchestrator). The data carries cents and a raw ETA
timestamp; the storefront presentation formats ``R$`` and the share text.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from django.utils import timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConfirmationItemProjection:
    """One ordered line on the confirmation page — cents only."""

    sku: str
    name: str
    qty: int
    unit_price_q: int
    line_total_q: int


@dataclass(frozen=True)
class OrderConfirmationProjection:
    """Confirmation data for a just-placed order — cents + raw ETA, no copy."""

    order_ref: str
    items: tuple[ConfirmationItemProjection, ...]
    total_q: int
    eta: datetime | None
    shop_name: str


def build_confirmation(order) -> OrderConfirmationProjection:
    """Build confirmation data for a just-placed order."""
    items = tuple(
        ConfirmationItemProjection(
            sku=item.sku,
            name=item.name or item.sku,
            qty=int(item.qty),
            unit_price_q=int(item.unit_price_q),
            line_total_q=int(item.line_total_q),
        )
        for item in order.items.all()
    )
    return OrderConfirmationProjection(
        order_ref=order.ref,
        items=items,
        total_q=int(order.total_q),
        eta=_eta(order),
        shop_name=_shop_name(),
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


__all__ = [
    "ConfirmationItemProjection",
    "OrderConfirmationProjection",
    "build_confirmation",
]
