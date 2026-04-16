"""ProductDetailProjection — read model for the storefront PDP.

Phase 1 / step 2 of the PROJECTION-UI-PLAN. Mirrors the discipline of
``build_catalog``: the builder orchestrates core services (``CatalogService``
for pricing + bundle expansion, ``stockman.availability`` for stock,
``services.alternatives`` for substitutes, ``services.storefront_context``
for companion discovery + session pricing) and emits a frozen, immutable
shape the PDP template consumes without ever touching Django model
instances.

Never imports from ``shopman.shop.web.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from shopman.offerman.models import CollectionItem, ListingItem, Product
from shopman.offerman.service import CatalogError, CatalogService
from shopman.utils.monetary import format_money

from shopman.shop.config import ChannelConfig
from shopman.shop.services.alternatives import find as find_alternatives
from shopman.shop.services.storefront_context import (
    companion_skus,
    session_pricing_hints,
)

from .catalog import (
    CatalogItemProjection,
    _cart_qty_by_sku,
    _resolve_availability,
    build_catalog_items_for_skus,
)
from .types import (
    AVAILABILITY_LABELS_PT,
    Availability,
    CategoryProjection,
    ComponentProjection,
)

if TYPE_CHECKING:
    from django.http import HttpRequest  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AllergenInfoProjection:
    """Allergen / dietary panel for a PDP.

    Every field is a display-ready string (or tuple) so the template can
    render without further formatting. ``None``/empty tuples mean the
    section should be hidden.
    """

    allergens: tuple[str, ...]
    dietary_info: tuple[str, ...]
    serves: str | None

    @property
    def has_any(self) -> bool:
        return bool(self.allergens or self.dietary_info or self.serves)


@dataclass(frozen=True)
class ConservationInfoProjection:
    """Shelf life / storage guidance panel for a PDP.

    Mirrors the v1 template: a ready-to-render ``shelf_life_label`` (pt-BR)
    plus the storage tip as the Product author wrote it.
    """

    shelf_life_label: str | None
    storage_tip: str | None
    unit_weight_label: str | None

    @property
    def has_any(self) -> bool:
        return bool(self.shelf_life_label or self.storage_tip or self.unit_weight_label)


@dataclass(frozen=True)
class ProductDetailProjection:
    """Full read model for the storefront PDP."""

    sku: str
    slug: str
    name: str
    short_description: str
    long_description: str
    image_url: str | None
    gallery: tuple[str, ...]

    # Price (dual)
    base_price_q: int
    price_display: str
    has_promotion: bool
    original_price_display: str | None
    promotion_label: str | None

    # Availability
    availability: Availability
    availability_label: str
    can_add_to_cart: bool
    available_qty: int | None
    max_qty: int

    # Cart state
    qty_in_cart: int

    # Bundle composition
    is_bundle: bool
    components: tuple[ComponentProjection, ...]

    # Dietary / allergen
    allergen: AllergenInfoProjection | None

    # Conservation / freshness
    conservation: ConservationInfoProjection | None

    # Breadcrumb
    breadcrumb_category: CategoryProjection | None

    # Recommendations
    alternatives: tuple[CatalogItemProjection, ...]
    suggestions: tuple[CatalogItemProjection, ...]


# ──────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────


def build_product_detail(
    *,
    sku: str,
    channel_ref: str,
    request: HttpRequest | None = None,
) -> ProductDetailProjection | None:
    """Build a ``ProductDetailProjection`` for ``sku``.

    Returns ``None`` if the product does not exist or is unpublished —
    callers convert that to a 404. Never raises for business conditions
    (paused, sold out, no listing); those become projection state.
    """
    product = Product.objects.filter(sku=sku, is_published=True).first()
    if product is None:
        return None

    config = ChannelConfig.for_channel(channel_ref)
    low_stock_threshold = Decimal(str(config.stock.low_stock_threshold))

    base_q = _listing_price_q(product, channel_ref) or product.base_price_q

    sku_collections = list(
        CollectionItem.objects.filter(product=product).values_list(
            "collection__ref", flat=True,
        )
    )

    ft_hint, sub_hint = session_pricing_hints(request)
    price = CatalogService.get_price(
        product.sku,
        qty=1,
        listing=channel_ref,
        context={
            "sku_collections": sku_collections,
            "session_total_q": sub_hint,
            "fulfillment_type": ft_hint,
        },
        list_unit_price_q=base_q,
    )

    has_promo = bool(
        price.adjustments and price.final_unit_price_q < price.list_unit_price_q,
    )
    promotion_label: str | None = None
    original_price_display: str | None = None
    if has_promo:
        adj = price.adjustments[0]
        promotion_label = adj.metadata.get("badge_label") or adj.label
        original_price_display = _money(price.list_unit_price_q)

    effective_q = price.final_unit_price_q

    # Availability — read raw once, resolve to canonical enum.
    raw_avail = _availability(product.sku, channel_ref)
    availability = _resolve_availability(
        raw_avail,
        product,
        low_stock_threshold=low_stock_threshold,
    )
    availability_label = AVAILABILITY_LABELS_PT[availability]
    can_add_to_cart = availability in (
        Availability.AVAILABLE,
        Availability.LOW_STOCK,
        Availability.PLANNED_OK,
    )
    available_qty = _promisable_int(raw_avail)

    # Bundle components — expand only if the product declares itself a bundle.
    components = _components(product)

    allergen = _allergen(product)
    conservation = _conservation(product)
    breadcrumb_category = _breadcrumb_category(product)

    # Alternatives only when unavailable; cross-sell only when available.
    alternatives: tuple[CatalogItemProjection, ...] = ()
    suggestions: tuple[CatalogItemProjection, ...] = ()
    if not can_add_to_cart:
        alt_skus = [a["sku"] for a in find_alternatives(product.sku, limit=4)]
        alternatives = build_catalog_items_for_skus(
            alt_skus, channel_ref=channel_ref, request=request,
        )
    else:
        suggestions = build_catalog_items_for_skus(
            companion_skus(product.sku, limit=3),
            channel_ref=channel_ref,
            request=request,
        )

    gallery = _gallery(product)

    qty_in_cart = int(_cart_qty_by_sku(request).get(product.sku, 0))

    return ProductDetailProjection(
        sku=product.sku,
        slug=product.sku,
        name=product.name,
        short_description=product.short_description or "",
        long_description=product.long_description or "",
        image_url=product.image_url or None,
        gallery=gallery,
        base_price_q=int(effective_q or 0),
        price_display=_money(effective_q) if effective_q else "",
        has_promotion=has_promo,
        original_price_display=original_price_display,
        promotion_label=promotion_label,
        availability=availability,
        availability_label=availability_label,
        can_add_to_cart=can_add_to_cart,
        available_qty=available_qty,
        max_qty=99,  # storefront cap; matches v1 <input max="99">
        qty_in_cart=qty_in_cart,
        is_bundle=product.is_bundle,
        components=components,
        allergen=allergen,
        conservation=conservation,
        breadcrumb_category=breadcrumb_category,
        alternatives=alternatives,
        suggestions=suggestions,
    )


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _listing_price_q(product: Product, channel_ref: str) -> int | None:
    item = (
        ListingItem.objects.filter(
            listing__ref=channel_ref,
            listing__is_active=True,
            product=product,
            is_published=True,
        )
        .order_by("-min_qty")
        .first()
    )
    return item.price_q if item else None


def _availability(sku: str, channel_ref: str) -> dict | None:
    try:
        from shopman.stockman.services.availability import (
            availability_for_sku,
            availability_scope_for_channel,
        )
    except ImportError:
        return None
    try:
        scope = availability_scope_for_channel(channel_ref)
        return availability_for_sku(
            sku,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
        )
    except Exception as e:
        logger.warning("pdp_availability_failed sku=%s: %s", sku, e, exc_info=True)
        return None


def _promisable_int(raw_avail: dict | None) -> int | None:
    if raw_avail is None:
        return None
    total = raw_avail.get("total_promisable")
    if total is None:
        return None
    try:
        return int(Decimal(str(total)))
    except (ValueError, ArithmeticError):
        return None


def _components(product: Product) -> tuple[ComponentProjection, ...]:
    if not product.is_bundle:
        return ()
    try:
        raw = CatalogService.expand(product.sku)
    except CatalogError:
        return ()
    except Exception:
        logger.exception("pdp_bundle_expand_failed sku=%s", product.sku)
        return ()
    return tuple(
        ComponentProjection(
            sku=str(entry.get("sku") or ""),
            name=str(entry.get("name") or ""),
            qty_display=_format_component_qty(entry.get("qty")),
        )
        for entry in raw
    )


def _format_component_qty(qty) -> str:
    if qty is None:
        return ""
    try:
        value = Decimal(str(qty))
    except (ValueError, ArithmeticError):
        return str(qty)
    if value == value.to_integral_value():
        return f"{int(value)}x"
    return f"{value.normalize()}x"


def _allergen(product: Product) -> AllergenInfoProjection | None:
    meta = product.metadata if isinstance(product.metadata, dict) else {}
    allergens_raw = meta.get("allergens") or []
    dietary_raw = meta.get("dietary_info") or []
    serves_raw = meta.get("serves")

    allergens = tuple(str(a) for a in allergens_raw if a) if isinstance(allergens_raw, list) else ()
    dietary = tuple(str(d) for d in dietary_raw if d) if isinstance(dietary_raw, list) else ()
    serves = str(serves_raw) if serves_raw else None

    if not (allergens or dietary or serves):
        return None
    return AllergenInfoProjection(
        allergens=allergens,
        dietary_info=dietary,
        serves=serves,
    )


def _conservation(product: Product) -> ConservationInfoProjection | None:
    shelf_life_label = _shelf_life_label(product.shelf_life_days)
    storage_tip = product.storage_tip.strip() if product.storage_tip else None
    unit_weight_label = (
        f"~{product.unit_weight_g}g a unidade" if product.unit_weight_g else None
    )
    if not (shelf_life_label or storage_tip or unit_weight_label):
        return None
    return ConservationInfoProjection(
        shelf_life_label=shelf_life_label,
        storage_tip=storage_tip,
        unit_weight_label=unit_weight_label,
    )


def _shelf_life_label(shelf_life_days: int | None) -> str | None:
    if shelf_life_days is None:
        return None
    if shelf_life_days == 0:
        return "Melhor consumido no mesmo dia"
    if shelf_life_days == 1:
        return "Melhor consumido em até 1 dia"
    return f"Conserva bem por {shelf_life_days} dias"


def _breadcrumb_category(product: Product) -> CategoryProjection | None:
    from django.urls import NoReverseMatch, reverse

    from .icons import collection_icon

    ci = (
        CollectionItem.objects.filter(product=product, collection__is_active=True)
        .select_related("collection")
        .order_by("collection__sort_order", "collection__name")
        .first()
    )
    if ci is None:
        return None
    col = ci.collection
    try:
        url = reverse("storefront:menu_collection", args=[col.ref])
    except NoReverseMatch:
        url = f"/menu/{col.ref}/"
    return CategoryProjection(
        ref=col.ref,
        name=col.name,
        icon=collection_icon(col.ref),
        url=url,
    )


def _gallery(product: Product) -> tuple[str, ...]:
    """Pull extra gallery URLs from ``metadata.gallery`` when present.

    Today ``Product`` has a single ``image_url``; authors can stash extras
    under ``metadata["gallery"]`` until we grow a proper M2M table. The PDP
    template renders whatever is returned — empty tuple = hide carousel.
    """
    meta = product.metadata if isinstance(product.metadata, dict) else {}
    raw = meta.get("gallery") or []
    if not isinstance(raw, list):
        return ()
    return tuple(str(url) for url in raw if url)


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"
