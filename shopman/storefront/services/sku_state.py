"""Storefront SKU availability state service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.shortcuts import get_object_or_404

from shopman.shop.config import ChannelConfig
from shopman.shop.projections.types import (
    AVAILABILITY_LABELS_PT,
    Availability,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkuState:
    sku: str
    availability: Availability
    available_qty: int | None
    can_add_to_cart: bool

    @property
    def label(self) -> str:
        return AVAILABILITY_LABELS_PT[self.availability]


def resolve(*, sku: str, channel_ref: str) -> SkuState:
    from shopman.offerman.models import Product

    product = get_object_or_404(Product, sku=sku)
    availability, available_qty, can_add = _resolve_state(
        sku=product.sku,
        is_sellable=product.is_sellable,
        channel_ref=channel_ref,
    )
    return SkuState(
        sku=sku,
        availability=availability,
        available_qty=available_qty,
        can_add_to_cart=can_add,
    )


def _resolve_state(
    *, sku: str, is_sellable: bool, channel_ref: str
) -> tuple[Availability, int | None, bool]:
    config = ChannelConfig.for_channel(channel_ref)
    low_stock_threshold = Decimal(str(config.stock.low_stock_threshold))

    raw_avail: dict | None
    try:
        from shopman.stockman.services.availability import availability_for_skus

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref)
        avail_map = availability_for_skus(
            [sku],
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
        raw_avail = avail_map.get(sku)
    except Exception:
        logger.warning(
            "SkuStateView: availability lookup failed sku=%s channel=%s",
            sku,
            channel_ref,
            exc_info=True,
        )
        raw_avail = None

    if not is_sellable:
        return Availability.UNAVAILABLE, 0, False

    if raw_avail is None:
        return Availability.AVAILABLE, None, True

    if raw_avail.get("is_paused", False):
        return Availability.UNAVAILABLE, 0, False

    policy = raw_avail.get("availability_policy", "planned_ok")
    total_promisable = raw_avail.get("total_promisable") or Decimal("0")
    if not isinstance(total_promisable, Decimal):
        total_promisable = Decimal(str(total_promisable))

    if policy == "demand_ok":
        return Availability.AVAILABLE, None, True

    if total_promisable <= 0:
        if policy == "planned_ok" and raw_avail.get("is_planned", False):
            return Availability.PLANNED_OK, 0, True
        return Availability.UNAVAILABLE, 0, False

    available_qty = int(total_promisable)
    if total_promisable <= low_stock_threshold:
        return Availability.LOW_STOCK, available_qty, True

    return Availability.AVAILABLE, available_qty, True
