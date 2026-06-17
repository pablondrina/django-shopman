"""Storefront catalog read service."""

from __future__ import annotations

import logging

from django.http import Http404

from shopman.shop.projections import catalog_context

logger = logging.getLogger(__name__)


def published_products(listing_ref: str | None):
    return catalog_context.published_products(listing_ref)


def ensure_active_collection(collection_ref: str):
    collection = catalog_context.get_active_collection(collection_ref)
    if collection is None:
        raise Http404
    return collection


def product_exists(sku: str) -> bool:
    return catalog_context.product_exists(sku)


def get_published_product(sku: str):
    return catalog_context.get_published_product(sku)


def get_sellable_published_product(sku: str):
    return catalog_context.get_sellable_published_product(sku)


def active_collections_with_counts() -> list[dict]:
    return catalog_context.active_collections_with_counts()


def search_index(catalog) -> list[dict]:
    """Build the lightweight client-side search index for the menu overlay."""
    seen: set[str] = set()
    records: list[dict] = []
    keywords_by_sku: dict[str, list[str]] = {}

    try:
        skus_all = [item.sku for sec in catalog.sections for item in sec.items]
        if skus_all:
            keywords_by_sku = catalog_context.keywords_by_sku(skus_all)
    except Exception:
        logger.debug("menu_search_index_keywords_failed", exc_info=True)
        keywords_by_sku = {}

    for section in catalog.sections:
        for item in section.items:
            if item.sku in seen:
                continue
            seen.add(item.sku)
            records.append({
                "sku": item.sku,
                "name": item.name,
                "price": item.price_display,
                "image": item.image_url or "",
                "section": section.label,
                "keywords": keywords_by_sku.get(item.sku, []),
                "terms": item.search_terms,
            })
    return records

