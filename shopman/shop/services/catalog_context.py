"""Canonical catalog read context for Shopman surfaces.

This module is the shop-level boundary for catalog, listing, price, and basic
availability reads. Storefront projections/services should depend on this file
instead of importing Offerman or Stockman directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import models

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BasicAvailability:
    """Small availability shape shared by catalog UI and neutral exports."""

    status: str
    available_qty: int | None
    can_add_to_cart: bool


def products_queryset():
    from shopman.offerman.models import Product

    return Product.objects.all()


def active_collections_queryset():
    from shopman.offerman.models import Collection

    return Collection.objects.filter(is_active=True)


def active_collections() -> list[Any]:
    return list(active_collections_queryset().order_by("sort_order", "name"))


def get_active_collection(collection_ref: str):
    return active_collections_queryset().filter(ref=collection_ref).first()


def listing_exists(listing_ref: str) -> bool:
    from shopman.offerman.models import Listing

    return Listing.objects.filter(ref=listing_ref, is_active=True).exists()


def get_product(sku: str):
    return products_queryset().filter(sku=sku).first()


def product_exists(sku: str) -> bool:
    return products_queryset().filter(sku=sku).exists()


def get_published_product(sku: str):
    return products_queryset().filter(sku=sku, is_published=True).first()


def get_sellable_published_product(sku: str):
    return products_queryset().filter(sku=sku, is_published=True, is_sellable=True).first()


def products_by_sku(skus: list[str], *, only_published: bool = True) -> dict[str, Any]:
    qs = products_queryset().filter(sku__in=skus)
    if only_published:
        qs = qs.filter(is_published=True)
    return {product.sku: product for product in qs}


def published_products(listing_ref: str | None = None):
    qs = products_queryset().filter(is_published=True)
    if listing_ref:
        qs = qs.filter(
            listing_items__listing__ref=listing_ref,
            listing_items__listing__is_active=True,
            listing_items__is_published=True,
        )
    return qs


def active_collections_with_counts() -> list[dict]:
    from shopman.offerman.models import CollectionItem

    data = []
    for collection in active_collections():
        count = CollectionItem.objects.filter(
            collection=collection,
            product__is_published=True,
        ).count()
        data.append({
            "ref": collection.ref,
            "name": collection.name,
            "description": getattr(collection, "description", None) or "",
            "product_count": count,
        })
    return data


def keywords_by_sku(skus: list[str]) -> dict[str, list[str]]:
    if not skus:
        return {}

    result: dict[str, list[str]] = {}
    for product in products_queryset().filter(sku__in=skus).prefetch_related("keywords"):
        try:
            result[product.sku] = [str(tag.name) for tag in product.keywords.all()]
        except Exception:
            result[product.sku] = []
    return result


def image_urls_by_sku(skus) -> dict[str, str | None]:
    sku_list = [sku for sku in skus if sku]
    if not sku_list:
        return {}
    return {
        product.sku: (product.image_url or None)
        for product in products_queryset().filter(sku__in=sku_list).only("sku", "image_url")
    }


def collection_refs_by_sku(skus: list[str]) -> dict[str, list[str]]:
    from shopman.offerman.models import CollectionItem

    result: dict[str, list[str]] = {}
    if not skus:
        return result
    for item in CollectionItem.objects.filter(product__sku__in=skus).select_related("collection", "product"):
        result.setdefault(item.product.sku, []).append(item.collection.ref)
    return result


def primary_collection_id_by_sku(skus: list[str]) -> dict[str, int]:
    from shopman.offerman.models import CollectionItem

    result: dict[str, int] = {}
    for item in CollectionItem.objects.filter(
        product__sku__in=skus,
        is_primary=True,
    ).select_related("collection", "product"):
        result[item.product.sku] = item.collection_id
    return result


def breadcrumb_collection(product):
    from shopman.offerman.models import CollectionItem

    item = (
        CollectionItem.objects.filter(product=product, collection__is_active=True)
        .select_related("collection")
        .order_by("collection__sort_order", "collection__name")
        .first()
    )
    return item.collection if item else None


def published_products_by_collection(
    *,
    listing_ref: str,
    active_collection: Any | None = None,
) -> list[tuple[str | None, list[Any]]]:
    """Return ordered (collection_ref | None, products) groups for a listing."""
    base = published_products(listing_ref)

    if active_collection is not None:
        products = list(
            base.filter(collection_items__collection=active_collection)
            .order_by("collection_items__sort_order", "name")
            .distinct()
        )
        return [(active_collection.ref, products)]

    groups: list[tuple[str | None, list[Any]]] = []
    for collection in active_collections():
        products = list(
            base.filter(collection_items__collection=collection)
            .order_by("collection_items__sort_order", "name")
            .distinct()
        )
        if products:
            groups.append((collection.ref, products))

    uncategorized = list(base.exclude(collection_items__isnull=False).order_by("name").distinct())
    if uncategorized:
        groups.append((None, uncategorized))
    return groups


def listing_price_map(
    skus: list[str],
    listing_ref: str,
    *,
    only_published: bool = True,
    only_sellable: bool = True,
) -> dict[str, int]:
    from shopman.offerman.models import ListingItem

    filters: dict[str, Any] = {
        "listing__ref": listing_ref,
        "listing__is_active": True,
        "product__sku__in": skus,
    }
    if only_published:
        filters["is_published"] = True
    if only_sellable:
        filters["is_sellable"] = True

    price_map: dict[str, int] = {}
    for item in (
        ListingItem.objects.filter(**filters)
        .select_related("product")
        .order_by("-min_qty")
    ):
        price_map.setdefault(item.product.sku, item.price_q)
    return price_map


def listing_price_for_product(product, listing_ref: str) -> int | None:
    return listing_price_map([product.sku], listing_ref, only_published=True, only_sellable=False).get(product.sku)


def listed_in_channel(product, channel_ref: str, *, fallback_when_listing_missing: bool = True) -> bool:
    """Return whether a product is publishable/sellable in a channel listing."""
    from shopman.offerman.models import ListingItem

    if fallback_when_listing_missing and not listing_exists(channel_ref):
        return True

    return ListingItem.objects.filter(
        listing__ref=channel_ref,
        listing__is_active=True,
        product=product,
        is_published=True,
        is_sellable=True,
    ).exists()


def contextual_price(
    sku: str,
    *,
    qty: Decimal | int = 1,
    listing_ref: str | None = None,
    context: dict | None = None,
    list_unit_price_q: int | None = None,
):
    from shopman.offerman.service import CatalogService

    return CatalogService.get_price(
        sku,
        qty=Decimal(str(qty)),
        listing=listing_ref,
        context=context,
        list_unit_price_q=list_unit_price_q,
    )


def expand_bundle(sku: str, qty: Decimal = Decimal("1")) -> list[dict]:
    from shopman.offerman.service import CatalogService

    return CatalogService.expand(sku, qty)


def availability_for_sku(
    sku: str,
    *,
    channel_ref: str,
    target_date: date | None = None,
) -> dict | None:
    try:
        from shopman.stockman.services.availability import availability_for_sku as _availability_for_sku

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref)
        return _availability_for_sku(
            sku,
            target_date=target_date,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
    except Exception as exc:
        logger.warning("availability_lookup_failed sku=%s channel=%s: %s", sku, channel_ref, exc, exc_info=True)
        return None


def availability_for_skus(skus: list[str], *, channel_ref: str) -> dict[str, dict | None]:
    if not skus:
        return {}
    try:
        from shopman.stockman.services.availability import availability_for_skus as _availability_for_skus

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref)
        return _availability_for_skus(
            skus,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
    except Exception as exc:
        logger.warning("batch_availability_failed channel=%s: %s", channel_ref, exc, exc_info=True)
        return {}


def availability_with_own_hold(raw_avail: dict | None, own_hold: int) -> dict | None:
    if raw_avail is None or own_hold <= 0:
        return raw_avail
    adjusted = dict(raw_avail)
    if adjusted.get("total_promisable") is not None:
        adjusted["total_promisable"] = Decimal(str(adjusted["total_promisable"])) + Decimal(own_hold)
    if adjusted.get("total_available") is not None:
        adjusted["total_available"] = Decimal(str(adjusted["total_available"])) + Decimal(own_hold)
    return adjusted


def basic_availability(
    raw_avail: dict | None,
    *,
    is_sellable: bool,
    low_stock_threshold: Decimal,
) -> BasicAvailability:
    if not is_sellable:
        return BasicAvailability("unavailable", 0, False)
    if raw_avail is None:
        return BasicAvailability("available", None, True)
    if raw_avail.get("is_paused", False):
        return BasicAvailability("unavailable", 0, False)

    policy = raw_avail.get("availability_policy", "planned_ok")
    total_promisable = raw_avail.get("total_promisable") or Decimal("0")
    if not isinstance(total_promisable, Decimal):
        total_promisable = Decimal(str(total_promisable))

    if policy == "demand_ok":
        return BasicAvailability("available", None, True)

    available_qty = int(total_promisable)
    if total_promisable <= 0:
        if policy == "planned_ok" and raw_avail.get("is_planned", False):
            return BasicAvailability("planned_ok", 0, True)
        return BasicAvailability("unavailable", 0, False)

    if total_promisable <= low_stock_threshold:
        return BasicAvailability("low_stock", available_qty, True)

    return BasicAvailability("available", available_qty, True)


def storefront_availability(raw_avail: dict | None, *, is_sellable: bool) -> dict | None:
    if raw_avail is None:
        return None

    is_paused = raw_avail.get("is_paused", False) or not is_sellable
    policy = raw_avail.get("availability_policy", "planned_ok")
    total_promisable = raw_avail.get("total_promisable", Decimal("0"))
    can_order = ((policy == "demand_ok") or total_promisable > 0) and not is_paused
    had_stock = can_order or raw_avail.get("is_planned", False) or total_promisable > 0
    if can_order:
        state = "available"
    elif had_stock and not is_paused:
        state = "sold_out"
    else:
        state = "unavailable"
    return {
        "available_qty": total_promisable,
        "can_order": can_order,
        "is_paused": is_paused,
        "had_stock": had_stock,
        "state": state,
        "availability_policy": policy,
    }


def promisable_int(raw_avail: dict | None) -> int | None:
    if raw_avail is None:
        return None
    total = raw_avail.get("total_promisable")
    if total is None:
        return None
    try:
        return int(Decimal(str(total)))
    except (ValueError, ArithmeticError):
        return None


def product_tags(product) -> tuple[str, ...]:
    try:
        return tuple(tag.name for tag in product.keywords.all())
    except Exception:
        return ()


def nutrition_facts(product):
    from shopman.offerman.nutrition import NutritionFacts

    return NutritionFacts.from_dict(product.nutrition_facts or {})


def nutrient_label(field_name: str) -> str:
    from shopman.offerman.nutrition import NUTRIENT_LABELS_PT

    return NUTRIENT_LABELS_PT[field_name]


def visible_listing_items(listing_ref: str):
    from shopman.offerman.models import ListingItem

    return (
        ListingItem.objects.filter(
            listing__ref=listing_ref,
            listing__is_active=True,
        )
        .select_related("listing", "product")
        .prefetch_related("product__keywords", "product__collection_items__collection")
        .order_by("product__sku", "min_qty")
    )


def listing_validity_q(prefix: str = "listing_items__listing__") -> models.Q:
    from django.utils import timezone

    today = timezone.localdate()
    return (
        models.Q(**{f"{prefix}valid_from__isnull": True}) | models.Q(**{f"{prefix}valid_from__lte": today})
    ) & (
        models.Q(**{f"{prefix}valid_until__isnull": True}) | models.Q(**{f"{prefix}valid_until__gte": today})
    )
