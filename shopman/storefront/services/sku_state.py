"""Storefront SKU availability state service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.http import Http404

from shopman.shop.config import ChannelConfig
from shopman.shop.projections.types import (
    AVAILABILITY_LABELS_PT,
    Availability,
)
from shopman.shop.services import catalog_context

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
    product = catalog_context.get_product(sku)
    if product is None:
        raise Http404
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

    raw_avail = catalog_context.availability_for_skus([sku], channel_ref=channel_ref).get(sku)
    resolved = catalog_context.basic_availability(
        raw_avail,
        is_sellable=is_sellable,
        low_stock_threshold=low_stock_threshold,
    )
    return Availability(resolved.status), resolved.available_qty, resolved.can_add_to_cart
