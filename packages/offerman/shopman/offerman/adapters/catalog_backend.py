"""Offerman catalog backend implementation."""

import logging
from decimal import Decimal

from shopman.offerman.exceptions import CatalogError
from shopman.offerman.protocols import BundleComponent, PriceInfo, ProductInfo, SkuValidation
from shopman.offerman.service import CatalogService

logger = logging.getLogger(__name__)


class OffermanCatalogBackend:
    """
    CatalogBackend implementation using Offerman's catalog service.

    This adapter allows other apps (Orderman, Stockman) to use Offerman
    as their catalog source without direct model access.
    """

    def get_product(self, sku: str) -> ProductInfo | None:
        """Return product by SKU."""
        product = CatalogService.get(sku)
        if not product:
            return None

        primary_collection = None
        primary_item = product.collection_items.filter(is_primary=True).first()
        if primary_item:
            primary_collection = primary_item.collection.ref

        return ProductInfo(
            sku=product.sku,
            name=product.name,
            description=product.long_description or None,
            category=primary_collection,
            unit=product.unit,
            is_bundle=product.is_bundle,
            base_price_q=product.base_price_q,
            is_published=product.is_published,
            is_sellable=product.is_sellable,
            keywords=list(product.keywords.names()) if product.keywords else None,
            image_url=product.image_url or None,
        )

    def get_price(
        self,
        sku: str,
        qty: Decimal = Decimal("1"),
        channel: str | None = None,
    ) -> PriceInfo:
        """Return price."""
        total_price_q = CatalogService.price(sku, qty=qty, channel=channel)
        unit_price_q = round(total_price_q / qty) if qty > 0 else total_price_q

        return PriceInfo(
            sku=sku,
            unit_price_q=unit_price_q,
            total_price_q=total_price_q,
            qty=qty,
            listing=channel,
        )

    def validate_sku(self, sku: str) -> SkuValidation:
        """Validate SKU."""
        return CatalogService.validate(sku)

    def expand_bundle(
        self, sku: str, qty: Decimal = Decimal("1")
    ) -> list[BundleComponent]:
        """Expand bundle."""
        try:
            components = CatalogService.expand(sku, qty)
            return [
                BundleComponent(
                    sku=comp["sku"],
                    name=comp["name"],
                    qty=comp["qty"],
                )
                for comp in components
            ]
        except CatalogError as exc:
            logger.warning("expand_bundle: failed to expand %s: %s", sku, exc)
            return []
