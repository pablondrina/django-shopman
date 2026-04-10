"""
Offerman public API.

CORE (essential):
    CatalogService.get(sku)      - Get product
    CatalogService.price(sku)    - Get price
    CatalogService.expand(sku)   - Expand bundle into components
    CatalogService.validate(sku) - Validate SKU

CONVENIENCE (helpers):
    CatalogService.search(...)   - Search products

LISTING / CHANNEL (per-channel availability):
    CatalogService.get_available_products(listing_ref) - Products available in listing
    CatalogService.is_product_available(product, listing_ref) - Check availability
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from shopman.offerman.exceptions import CatalogError

if TYPE_CHECKING:
    from shopman.offerman.models import Product
    from shopman.offerman.protocols import SkuValidation


class CatalogService:
    """
    Offerman public API.

    Uses @classmethod for extensibility (see spec 000 section 12.1).

    CORE (essential):
        get(sku)      - Get product
        price(sku)    - Get price (base_price or via pricing backend)
        expand(sku)   - Expand bundle into components
        validate(sku) - Validate SKU

    CONVENIENCE (helpers):
        search(...)   - Search products
    """

    # ======================================================================
    # CORE API
    # ======================================================================

    @classmethod
    def get(cls, sku: str | list[str]) -> "Product | dict[str, Product] | None":
        from shopman.offerman.models import Product

        if isinstance(sku, list):
            products = Product.objects.filter(sku__in=sku)
            return {p.sku: p for p in products}
        return cls._fetch_product(sku)

    @classmethod
    def _fetch_product(cls, sku: str) -> "Product | None":
        from shopman.offerman.models import Product

        return Product.objects.filter(sku=sku).first()

    @classmethod
    def unit_price(
        cls,
        sku: str,
        qty: Decimal = Decimal("1"),
        channel: str | None = None,
        listing: str | None = None,
    ) -> int:
        """
        Return the per-unit price (in centavos) for the given qty tier.

        Uses min_qty cascading: finds the ListingItem with the highest
        min_qty that is <= qty. Falls back to base_price_q.
        """
        if qty <= 0:
            raise CatalogError("INVALID_QUANTITY", sku=sku, qty=str(qty))

        product = cls.get(sku)
        if not product:
            raise CatalogError("SKU_NOT_FOUND", sku=sku)

        effective_listing = listing or channel
        if effective_listing:
            tier_price = cls._get_price_from_listing(product, effective_listing, qty)
            if tier_price is not None:
                return tier_price

        return product.base_price_q

    @classmethod
    def price(
        cls,
        sku: str,
        qty: Decimal = Decimal("1"),
        channel: str | None = None,
        listing: str | None = None,
    ) -> int:
        up = cls.unit_price(sku, qty=qty, channel=channel, listing=listing)
        return int(Decimal(str(up * qty)).to_integral_value(rounding=ROUND_HALF_UP))

    @classmethod
    def _get_price_from_listing(
        cls,
        product: "Product",
        listing_ref: str,
        qty: Decimal,
    ) -> int | None:
        try:
            from shopman.offerman.models import Listing, ListingItem

            listing = Listing.objects.filter(ref=listing_ref).first()
            if not listing or not listing.is_valid():
                return None

            item = (
                ListingItem.objects.filter(
                    listing=listing,
                    product=product,
                    min_qty__lte=qty,
                    is_published=True,
                    is_available=True,
                )
                .order_by("-min_qty")
                .first()
            )

            return item.price_q if item else None

        except (ImportError, LookupError, ValueError):
            return None

    @classmethod
    def expand(cls, sku: str, qty: Decimal = Decimal("1")) -> list[dict]:
        product = cls.get(sku)
        if not product:
            raise CatalogError("SKU_NOT_FOUND", sku=sku)

        if not product.is_bundle:
            raise CatalogError("NOT_A_BUNDLE", sku=sku)

        return [
            {
                "sku": comp.component.sku,
                "name": comp.component.name,
                "qty": comp.qty * qty,
            }
            for comp in product.components.select_related("component")
        ]

    @classmethod
    def validate(cls, sku: str) -> "SkuValidation":
        from shopman.offerman.protocols import SkuValidation

        product = cls.get(sku)

        if not product:
            return SkuValidation(
                valid=False,
                sku=sku,
                error_code="not_found",
                message=f"SKU '{sku}' not found",
            )

        return SkuValidation(
            valid=True,
            sku=sku,
            name=product.name,
            is_published=product.is_published,
            is_available=product.is_available,
            message=cls._get_validation_message(product),
        )

    @classmethod
    def _get_validation_message(cls, product: "Product") -> str | None:
        if not product.is_published:
            return "Product is not published in catalog"
        if not product.is_available:
            return "Product is not available for purchase"
        return None

    # ======================================================================
    # CONVENIENCE API
    # ======================================================================

    @classmethod
    def search(
        cls,
        query: str | None = None,
        collection: str | None = None,
        keywords: list[str] | None = None,
        only_published: bool = True,
        only_available: bool = True,
        limit: int = 20,
    ) -> list["Product"]:
        from shopman.offerman.models import Product

        qs = Product.objects.all()

        if only_published:
            qs = qs.filter(is_published=True)
        if only_available:
            qs = qs.filter(is_available=True)
        if query:
            qs = qs.filter(
                models.Q(sku__icontains=query) | models.Q(name__icontains=query)
            ).distinct()

        if collection:
            qs = qs.filter(collection_items__collection__slug=collection)
        if keywords:
            qs = qs.filter(keywords__name__in=keywords).distinct()

        return list(qs[:limit])

    # ======================================================================
    # LISTING / CHANNEL API
    # ======================================================================

    @classmethod
    def _listing_validity_q(cls, prefix: str = "listing_items__listing__") -> models.Q:
        today = timezone.localdate()
        return (
            models.Q(**{f"{prefix}valid_from__isnull": True}) | models.Q(**{f"{prefix}valid_from__lte": today})
        ) & (
            models.Q(**{f"{prefix}valid_until__isnull": True}) | models.Q(**{f"{prefix}valid_until__gte": today})
        )

    @classmethod
    def get_available_products(cls, listing_ref: str) -> models.QuerySet["Product"]:
        from shopman.offerman.models import Product

        return Product.objects.filter(
            cls._listing_validity_q(),
            is_published=True,
            is_available=True,
            listing_items__listing__ref=listing_ref,
            listing_items__listing__is_active=True,
            listing_items__is_published=True,
            listing_items__is_available=True,
        ).distinct()

    @classmethod
    def is_product_available(cls, product: "Product", listing_ref: str) -> bool:
        if not product.is_published or not product.is_available:
            return False

        from shopman.offerman.models import ListingItem

        today = timezone.localdate()
        return ListingItem.objects.filter(
            models.Q(listing__valid_from__isnull=True) | models.Q(listing__valid_from__lte=today),
            models.Q(listing__valid_until__isnull=True) | models.Q(listing__valid_until__gte=today),
            listing__ref=listing_ref,
            listing__is_active=True,
            product=product,
            is_published=True,
            is_available=True,
        ).exists()
