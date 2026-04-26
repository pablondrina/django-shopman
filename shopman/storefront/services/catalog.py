"""Storefront catalog read service."""

from __future__ import annotations

from django.http import Http404
from django.urls import reverse

from shopman.shop.services import catalog_context


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
            })
    return records


def sitemap_urls(request) -> list[dict]:
    from shopman.shop.models import Shop

    urls = []
    base = request.build_absolute_uri("/").rstrip("/")

    shop = Shop.load()
    shop_updated = shop.updated_at.isoformat() if shop and getattr(shop, "updated_at", None) else None

    urls.append({
        "loc": base + reverse("storefront:home"),
        "priority": "1.0",
        "changefreq": "weekly",
        "lastmod": shop_updated,
    })
    urls.append({
        "loc": base + reverse("storefront:menu"),
        "priority": "1.0",
        "changefreq": "daily",
        "lastmod": shop_updated,
    })
    urls.append({
        "loc": base + reverse("storefront:como_funciona"),
        "priority": "0.5",
        "changefreq": "monthly",
        "lastmod": shop_updated,
    })

    for collection in catalog_context.active_collections():
        urls.append({
            "loc": base + reverse("storefront:menu_collection", args=[collection.ref]),
            "priority": "0.8",
            "changefreq": "daily",
            "lastmod": (
                collection.updated_at.isoformat()
                if getattr(collection, "updated_at", None)
                else None
            ),
        })

    for product in catalog_context.published_products():
        image_url = None
        if getattr(product, "image", None) and getattr(product.image, "name", ""):
            image_url = request.build_absolute_uri(product.image.url)
        elif getattr(product, "image_url", ""):
            url = product.image_url
            image_url = url if url.startswith("http") else base + url

        urls.append({
            "loc": base + reverse("storefront:product_detail", args=[product.sku]),
            "priority": "0.7",
            "changefreq": "daily",
            "lastmod": product.updated_at.isoformat() if getattr(product, "updated_at", None) else None,
            "image_url": image_url,
            "image_title": product.name,
        })

    return urls
