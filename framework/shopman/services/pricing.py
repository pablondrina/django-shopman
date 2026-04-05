"""
Pricing resolution service.

Core: CatalogService.price()
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.offering.service import CatalogService

logger = logging.getLogger(__name__)


def resolve(sku: str, qty: int = 1, channel: str | None = None) -> int:
    """
    Resolve the price for a SKU.

    Calls CatalogService.price() as the base price. In the future (R5),
    the Rules engine will apply modifiers on top.

    Args:
        sku: Product SKU
        qty: Quantity
        channel: Optional channel ref for listing-based pricing

    Returns:
        Total price in centavos (_q) for the given quantity.

    SYNC — immediate price resolution.
    """
    return CatalogService.price(sku, qty=Decimal(str(qty)), channel=channel)
