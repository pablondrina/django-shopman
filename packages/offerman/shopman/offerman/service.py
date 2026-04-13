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
    CatalogService.get_listed_products(listing_ref) - Products structurally linked to listing
    CatalogService.get_published_products(listing_ref) - Products visible in listing
    CatalogService.get_sellable_products(listing_ref) - Products strategically sellable in listing
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from django.db import models
from django.utils import timezone

from shopman.offerman.conf import get_pricing_backend, get_projection_backend
from shopman.offerman.exceptions import CatalogError
from shopman.offerman.protocols import ContextualPrice, ProjectedItem, ProjectionResult

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
    def _get_valid_listing(cls, listing_ref: str):
        from shopman.offerman.models import Listing

        listing = Listing.objects.filter(ref=listing_ref).first()
        if not listing:
            raise CatalogError("LISTING_NOT_FOUND", listing_ref=listing_ref)
        if not listing.is_valid():
            raise CatalogError("LISTING_NOT_ACTIVE", listing_ref=listing_ref)
        return listing

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
    def get_price(
        cls,
        sku: str,
        qty: Decimal = Decimal("1"),
        channel: str | None = None,
        listing: str | None = None,
        context: dict | None = None,
        *,
        list_unit_price_q: int | None = None,
    ) -> ContextualPrice:
        """
        Return the canonical commercial quote for a SKU in context.

        Offerman owns the list price and channel tiers. Optional contextual
        pricing may further adjust this quote via a configured backend, but the
        list price always remains explicit in the payload.
        """
        effective_listing = listing or channel
        if list_unit_price_q is None:
            list_unit_price_q = cls.unit_price(sku, qty=qty, channel=channel, listing=listing)
        list_total_price_q = int(
            Decimal(str(list_unit_price_q * qty)).to_integral_value(rounding=ROUND_HALF_UP)
        )

        pricing_backend = get_pricing_backend()
        if pricing_backend is None:
            return ContextualPrice(
                sku=sku,
                qty=qty,
                listing=effective_listing,
                list_unit_price_q=list_unit_price_q,
                list_total_price_q=list_total_price_q,
                final_unit_price_q=list_unit_price_q,
                final_total_price_q=list_total_price_q,
                adjustments=[],
                metadata={"source": "list_price", "context": context or {}},
            )

        price = pricing_backend.get_price(
            sku=sku,
            qty=qty,
            listing=effective_listing,
            list_unit_price_q=list_unit_price_q,
            list_total_price_q=list_total_price_q,
            context=context,
        )
        if price is None:
            return ContextualPrice(
                sku=sku,
                qty=qty,
                listing=effective_listing,
                list_unit_price_q=list_unit_price_q,
                list_total_price_q=list_total_price_q,
                final_unit_price_q=list_unit_price_q,
                final_total_price_q=list_total_price_q,
                adjustments=[],
                metadata={"source": "list_price", "context": context or {}},
            )
        return price

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
                    is_sellable=True,
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
            is_sellable=product.is_sellable,
            message=cls._get_validation_message(product),
        )

    @classmethod
    def _get_validation_message(cls, product: "Product") -> str | None:
        if not product.is_published:
            return "Product is not published in catalog"
        if not product.is_sellable:
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
        only_sellable: bool = True,
        limit: int = 20,
    ) -> list["Product"]:
        from shopman.offerman.models import Product

        qs = Product.objects.all()

        if only_published:
            qs = qs.filter(is_published=True)
        if only_sellable:
            qs = qs.sellable()
        if query:
            qs = qs.filter(
                models.Q(sku__icontains=query) | models.Q(name__icontains=query)
            ).distinct()

        if collection:
            qs = qs.filter(collection_items__collection__ref=collection)
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
    def get_listed_products(cls, listing_ref: str) -> models.QuerySet["Product"]:
        from shopman.offerman.models import Product

        return Product.objects.filter(
            cls._listing_validity_q(),
            listing_items__listing__ref=listing_ref,
            listing_items__listing__is_active=True,
        ).distinct()

    @classmethod
    def is_product_listed(cls, product: "Product", listing_ref: str) -> bool:
        from shopman.offerman.models import ListingItem

        today = timezone.localdate()
        return ListingItem.objects.filter(
            models.Q(listing__valid_from__isnull=True) | models.Q(listing__valid_from__lte=today),
            models.Q(listing__valid_until__isnull=True) | models.Q(listing__valid_until__gte=today),
            listing__ref=listing_ref,
            listing__is_active=True,
            product=product,
        ).exists()

    @classmethod
    def get_published_products(cls, listing_ref: str) -> models.QuerySet["Product"]:
        return cls.get_listed_products(listing_ref).filter(
            is_published=True,
            listing_items__listing__ref=listing_ref,
            listing_items__listing__is_active=True,
            listing_items__is_published=True,
        ).distinct()

    @classmethod
    def is_product_published(cls, product: "Product", listing_ref: str) -> bool:
        if not product.is_published:
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
        ).exists()

    @classmethod
    def get_sellable_products(cls, listing_ref: str) -> models.QuerySet["Product"]:
        return cls.get_listed_products(listing_ref).filter(
            is_sellable=True,
            listing_items__listing__ref=listing_ref,
            listing_items__listing__is_active=True,
            listing_items__is_sellable=True,
        ).distinct()

    @classmethod
    def is_product_sellable(cls, product: "Product", listing_ref: str) -> bool:
        if not product.is_sellable:
            return False

        from shopman.offerman.models import ListingItem

        today = timezone.localdate()
        return ListingItem.objects.filter(
            models.Q(listing__valid_from__isnull=True) | models.Q(listing__valid_from__lte=today),
            models.Q(listing__valid_until__isnull=True) | models.Q(listing__valid_until__gte=today),
            listing__ref=listing_ref,
            listing__is_active=True,
            product=product,
            is_sellable=True,
        ).exists()

    @classmethod
    def get_projection_items(cls, listing_ref: str) -> list[ProjectedItem]:
        """
        Return the normalized channel snapshot for a valid listing.

        This is the canonic representation of a channel-specific commercial
        offering: one row per listed product, with listing price plus the final
        published/sellable state after combining product- and listing-level
        switches.
        """
        from shopman.offerman.models import ListingItem

        listing = cls._get_valid_listing(listing_ref)
        items = (
            ListingItem.objects.filter(listing=listing)
            .select_related("product")
            .prefetch_related("product__keywords", "product__collection_items__collection")
            .order_by("product__sku", "-min_qty")
        )

        snapshot: dict[str, ProjectedItem] = {}
        for item in items:
            if item.product.sku in snapshot:
                continue

            product = item.product
            primary_collection = None
            primary_item = product.collection_items.filter(is_primary=True).first()
            if primary_item:
                primary_collection = primary_item.collection.ref

            snapshot[product.sku] = ProjectedItem(
                sku=product.sku,
                name=product.name,
                description=product.long_description or product.short_description,
                unit=product.unit,
                price_q=item.price_q,
                is_published=product.is_published and item.is_published,
                is_sellable=product.is_sellable and item.is_sellable,
                category=primary_collection,
                image_url=product.image_url or None,
                keywords=list(product.keywords.names()) if product.keywords else [],
                metadata={
                    "listing_ref": listing.ref,
                    "listing_name": listing.name,
                    "listing_priority": listing.priority,
                    "min_qty": str(item.min_qty),
                },
            )

        return list(snapshot.values())

    @classmethod
    def project_listing(cls, listing_ref: str, *, full_sync: bool = False) -> ProjectionResult:
        """
        Project the current listing snapshot to its external channel backend.

        Published + sellable items are upserted through the backend. Listed
        items that are no longer published or sellable are retracted on
        incremental syncs.
        """
        backend = get_projection_backend(listing_ref)
        if backend is None:
            raise CatalogError("PROJECTION_BACKEND_NOT_CONFIGURED", channel=listing_ref)

        items = cls.get_projection_items(listing_ref)
        projectable = [item for item in items if item.is_published and item.is_sellable]
        retracted = [item.sku for item in items if not (item.is_published and item.is_sellable)]

        project_result = backend.project(projectable, channel=listing_ref, full_sync=full_sync)
        errors = list(project_result.errors)
        success = project_result.success
        projected = project_result.projected

        if retracted and not full_sync:
            retract_result = backend.retract(retracted, channel=listing_ref)
            success = success and retract_result.success
            errors.extend(retract_result.errors)

        return ProjectionResult(
            success=success,
            projected=projected,
            errors=errors,
            channel=listing_ref,
        )
