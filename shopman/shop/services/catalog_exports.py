"""Neutral catalog export contracts.

The payloads in this module are intentionally platform-neutral. Adapters for
Google, WhatsApp, Meta/IG, or marketplaces should translate this shape into
their API-specific schemas outside this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from shopman.shop.services import catalog_context


@dataclass(frozen=True)
class CatalogExportPrice:
    amount_q: int
    currency: str = "BRL"
    unit: str = "unit"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogExportAvailability:
    status: str
    available_qty: int | None
    channel: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogExportItem:
    product: str
    listing: str
    ref: str
    sku: str
    name: str
    description: str
    images: tuple[str, ...]
    price: CatalogExportPrice
    availability: CatalogExportAvailability
    channel: str
    status: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CatalogExportPayload:
    listing: str
    channel: str
    status: str
    items: tuple[CatalogExportItem, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_catalog_export(
    *,
    listing_ref: str,
    channel: str | None = None,
    include_inactive: bool = False,
    low_stock_threshold: Decimal = Decimal("5"),
) -> CatalogExportPayload:
    """Build a neutral export payload from an Offerman listing snapshot."""
    export_channel = channel or listing_ref
    items: list[CatalogExportItem] = []

    seen: set[str] = set()
    for listing_item in catalog_context.visible_listing_items(listing_ref):
        product = listing_item.product
        if product.sku in seen:
            continue
        seen.add(product.sku)

        status = _item_status(product=product, listing_item=listing_item)
        if status != "active" and not include_inactive:
            continue

        raw_avail = catalog_context.availability_for_sku(product.sku, channel_ref=export_channel)
        basic_avail = catalog_context.basic_availability(
            raw_avail,
            is_sellable=product.is_sellable and listing_item.is_sellable,
            low_stock_threshold=low_stock_threshold,
        )

        metadata = _product_metadata(product)
        metadata.update({
            "listing_item_id": listing_item.pk,
            "min_qty": str(listing_item.min_qty),
            "unit": product.unit,
            "tags": list(catalog_context.product_tags(product)),
        })

        items.append(
            CatalogExportItem(
                product=str(product.uuid),
                listing=listing_ref,
                ref=f"{listing_ref}:{product.sku}",
                sku=product.sku,
                name=product.name,
                description=product.long_description or product.short_description or "",
                images=_images(product),
                price=CatalogExportPrice(
                    amount_q=int(listing_item.price_q),
                    metadata={"source": "listing_item"},
                ),
                availability=CatalogExportAvailability(
                    status=basic_avail.status,
                    available_qty=basic_avail.available_qty,
                    channel=export_channel,
                    metadata=_availability_metadata(raw_avail),
                ),
                channel=export_channel,
                status=status,
                metadata=metadata,
            )
        )

    payload_status = "active" if items else "empty"
    return CatalogExportPayload(
        listing=listing_ref,
        channel=export_channel,
        status=payload_status,
        items=tuple(items),
        metadata={"source": "offerman", "contract": "catalog_export.v1"},
    )


def build_catalog_export_dict(**kwargs) -> dict[str, Any]:
    return build_catalog_export(**kwargs).as_dict()


def _item_status(*, product, listing_item) -> str:
    if product.is_published and product.is_sellable and listing_item.is_published and listing_item.is_sellable:
        return "active"
    if product.is_published and listing_item.is_published:
        return "paused"
    return "inactive"


def _images(product) -> tuple[str, ...]:
    images: list[str] = []
    if product.image_url:
        images.append(product.image_url)
    meta = product.metadata if isinstance(product.metadata, dict) else {}
    gallery = meta.get("gallery") or []
    if isinstance(gallery, list):
        images.extend(str(url) for url in gallery if url)
    return tuple(dict.fromkeys(images))


def _product_metadata(product) -> dict[str, Any]:
    meta = product.metadata if isinstance(product.metadata, dict) else {}
    safe = dict(meta)
    safe.pop("gallery", None)
    return safe


def _availability_metadata(raw_avail: dict | None) -> dict[str, Any]:
    if raw_avail is None:
        return {"source": "catalog"}
    return {
        "source": "stockman",
        "availability_policy": raw_avail.get("availability_policy"),
        "is_paused": bool(raw_avail.get("is_paused", False)),
        "is_planned": bool(raw_avail.get("is_planned", False)),
    }
