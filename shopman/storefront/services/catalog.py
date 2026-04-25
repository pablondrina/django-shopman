"""Storefront catalog read service."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.urls import reverse


def published_products(listing_ref: str | None):
    from shopman.offerman.models import Product

    qs = Product.objects.filter(is_published=True)
    if listing_ref:
        qs = qs.filter(
            listing_items__listing__ref=listing_ref,
            listing_items__listing__is_active=True,
            listing_items__is_published=True,
        )
    return qs


def ensure_active_collection(collection_ref: str):
    from shopman.offerman.models import Collection

    return get_object_or_404(Collection, ref=collection_ref, is_active=True)


def product_exists(sku: str) -> bool:
    from shopman.offerman.models import Product

    return Product.objects.filter(sku=sku).exists()


def get_published_product(sku: str):
    from shopman.offerman.models import Product

    return Product.objects.filter(sku=sku, is_published=True).first()


def get_sellable_published_product(sku: str):
    from shopman.offerman.models import Product

    return Product.objects.filter(sku=sku, is_published=True, is_sellable=True).first()


def active_collections_with_counts() -> list[dict]:
    from shopman.offerman.models import Collection, CollectionItem

    data = []
    for collection in Collection.objects.filter(is_active=True).order_by("sort_order", "name"):
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


def search_index(catalog) -> list[dict]:
    """Build the lightweight client-side search index for the menu overlay."""
    from shopman.offerman.models import Product

    seen: set[str] = set()
    records: list[dict] = []
    keywords_by_sku: dict[str, list[str]] = {}

    try:
        skus_all = [item.sku for sec in catalog.sections for item in sec.items]
        if skus_all:
            products = Product.objects.filter(sku__in=skus_all).prefetch_related("keywords")
            for product in products:
                try:
                    keywords_by_sku[product.sku] = [str(tag.name) for tag in product.keywords.all()]
                except Exception:
                    keywords_by_sku[product.sku] = []
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
    from shopman.offerman.models import Collection, Product

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

    for collection in Collection.objects.filter(is_active=True):
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

    for product in Product.objects.filter(is_published=True):
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
