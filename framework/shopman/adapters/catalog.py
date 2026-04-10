"""
Internal catalog adapter — delegates to Offerman (Core).

Core: CatalogService (pricing, bundle expansion), Product, Listing, ListingItem, CollectionItem
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_price(sku: str, qty: int = 1, channel: str | None = None) -> int:
    """Preço em centavos. Delega para CatalogService.price()."""
    from decimal import Decimal

    from shopman.offerman.service import CatalogService

    return CatalogService.price(sku, qty=Decimal(str(qty)), channel=channel)


def expand_bundle(sku: str, qty) -> list[dict]:
    """Expande bundle em componentes. Retorna [{"sku": str, "qty": Decimal}]."""
    from shopman.offerman.service import CatalogService

    return CatalogService.expand(sku, qty)


def get_product_base_price(sku: str) -> int:
    """Preço base do produto (sem tiers). Retorna centavos."""
    from shopman.offerman.models import Product

    return Product.objects.get(sku=sku).base_price_q


def get_listing_item(sku: str, listing_ref: str) -> dict | None:
    """Retorna {"price_q": int, "min_qty": int, "is_available": bool} ou None."""
    from shopman.offerman.models import ListingItem

    try:
        item = ListingItem.objects.get(
            listing__ref=listing_ref,
            listing__is_active=True,
            product__sku=sku,
            is_published=True,
            is_available=True,
        )
    except ListingItem.DoesNotExist:
        return None
    except ListingItem.MultipleObjectsReturned:
        item = (
            ListingItem.objects.filter(
                listing__ref=listing_ref,
                listing__is_active=True,
                product__sku=sku,
                is_published=True,
                is_available=True,
            ).first()
        )
        if not item:
            return None

    return {"price_q": item.price_q, "min_qty": item.min_qty, "is_available": item.is_available}


def find_listing_tiers(sku: str, listing_ref: str) -> list[dict]:
    """Tiers de preço por quantidade. Retorna [{"min_qty": int, "price_q": int, "is_available": bool}] desc."""
    from shopman.offerman.models import ListingItem

    return list(
        ListingItem.objects.filter(
            listing__ref=listing_ref,
            product__sku=sku,
            is_published=True,
        )
        .order_by("-min_qty")
        .values("min_qty", "price_q", "is_available")
    )


def listing_exists(listing_ref: str) -> bool:
    """Verifica se um Listing ativo existe para o listing_ref."""
    from shopman.offerman.models import Listing

    return Listing.objects.filter(ref=listing_ref, is_active=True).exists()


def bulk_sku_to_collection_id(skus: list[str]) -> dict[str, int]:
    """Mapa sku → collection_id (primary) para múltiplos SKUs."""
    from shopman.offerman.models import CollectionItem

    result: dict[str, int] = {}
    for ci in CollectionItem.objects.filter(
        product__sku__in=skus, is_primary=True,
    ).select_related("collection"):
        result[ci.product.sku] = ci.collection_id
    return result


def find_alternatives(sku: str, limit: int = 8) -> list:
    """Busca alternativas para o SKU via Offerman."""
    from shopman.offerman import find_alternatives as _find_alternatives

    return _find_alternatives(sku, limit=limit)


def bulk_listing_price_map(skus: list[str], listing_ref: str) -> dict[str, int]:
    """Mapa sku → price_q do listing para múltiplos SKUs (preço mais específico por qty)."""
    from shopman.offerman.models import ListingItem

    price_map: dict[str, int] = {}
    for item in (
        ListingItem.objects.filter(
            listing__ref=listing_ref,
            listing__is_active=True,
            product__sku__in=skus,
            is_published=True,
            is_available=True,
        )
        .select_related("product")
        .order_by("-min_qty")
    ):
        price_map.setdefault(item.product.sku, item.price_q)
    return price_map
