"""
Shopman Simple Pricing Adapter — Adapter para precificação simples.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from django.core.exceptions import ObjectDoesNotExist

logger = logging.getLogger(__name__)


class SimplePricingBackend:
    """
    Adapter para precificação simples via Product.price_q.
    """

    def __init__(self, product_resolver: Callable[[str], Any]):
        self.get_product = product_resolver

    def get_price(self, sku: str, channel: Any) -> int | None:
        try:
            product = self.get_product(sku)
            return product.base_price_q
        except ObjectDoesNotExist:
            return None
        except Exception:
            logger.exception("Unexpected error in SimplePricingBackend.get_price for sku=%s", sku)
            return None


class ChannelPricingBackend:
    """
    Adapter para precificação por canal.

    Busca preço em ChannelListing primeiro, fallback para Product.price_q.
    """

    def __init__(
        self,
        product_resolver: Callable[[str], Any],
        listing_resolver: Callable[[str, str], Any] | None = None,
    ):
        self.get_product = product_resolver
        self.get_listing = listing_resolver

    def get_price(self, sku: str, channel: Any) -> int | None:
        # Tenta listing primeiro
        if self.get_listing:
            try:
                listing = self.get_listing(sku, channel.ref)
                if hasattr(listing, "price_q") and listing.price_q is not None:
                    return listing.price_q
            except ObjectDoesNotExist:
                pass
            except Exception:
                logger.exception("Unexpected error in ChannelPricingBackend.get_price listing lookup for sku=%s", sku)
                pass  # Fall through to product fallback

        # Fallback para product
        try:
            product = self.get_product(sku)
            return product.base_price_q
        except ObjectDoesNotExist:
            return None
        except Exception:
            logger.exception("Unexpected error in ChannelPricingBackend.get_price product fallback for sku=%s", sku)
            return None
