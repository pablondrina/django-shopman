"""CatalogProjection — read model for the storefront menu/catalog.

Phase 1 pilot of the PROJECTION-UI-PLAN. The builder orchestrates core
services (``CatalogService`` for pricing, ``stockman.availability`` for
stock, ``services.storefront_context`` for session/happy-hour/popularity)
and emits a frozen, immutable shape the templates consume without ever
touching Django model instances.

The projection never imports from ``shopman.storefront.views.*`` — everything it
needs lives under ``services`` or in sibling projection modules. Business
rules like the low-stock threshold come from ``ChannelConfig`` so they're
Admin-configurable per channel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING

from django.urls import NoReverseMatch, reverse
from shopman.offerman.models import (
    Collection,
    CollectionItem,
    ListingItem,
    Product,
)
from shopman.offerman.service import CatalogService
from shopman.utils.monetary import format_money

from shopman.shop.config import ChannelConfig
from shopman.storefront.services.storefront_context import (
    happy_hour_state,
    popular_skus,
    session_pricing_hints,
)

from shopman.storefront.projections.icons import collection_icon
from shopman.shop.projections.types import (
    AVAILABILITY_LABELS_PT,
    Availability,
    CategoryProjection,
    HappyHourProjection,
)

if TYPE_CHECKING:
    from django.http import HttpRequest  # noqa: F401

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogItemProjection:
    """A single catalog line as rendered by the storefront."""

    sku: str
    slug: str
    name: str
    short_description: str
    image_url: str | None
    category: str | None
    tags: tuple[str, ...]

    # Price (dual: raw + display)
    base_price_q: int
    price_display: str
    has_promotion: bool
    original_price_display: str | None
    promotion_label: str | None

    # Availability (canonical enum + pt-BR label)
    availability: Availability
    availability_label: str
    can_add_to_cart: bool

    # Dietary / attributes
    dietary_info: tuple[str, ...]
    is_new: bool
    is_featured: bool

    # Cart state (populated when the builder receives a request)
    allergens: tuple[str, ...] = ()
    qty_in_cart: int = 0

    # Available quantity for stock-aware UX. None = demand-based/untracked
    # (sem teto). Integer = exato. Permite o menu abrir o modal de estoque
    # client-side quando requested > available, sem esperar o POST falhar.
    available_qty: int | None = None

    # Allergens from product.metadata["allergens"] — shown as inline badge.
    allergens: tuple[str, ...] = field(default_factory=tuple)

    @property
    def detail_url(self) -> str:
        """Convenience for templates — build the PDP URL."""
        try:
            return reverse("storefront:product_detail", args=[self.sku])
        except NoReverseMatch:
            return f"/produto/{self.sku}/"


@dataclass(frozen=True)
class CatalogSectionProjection:
    """A grouping of items under a category or a dynamic collection.

    - ``category`` populated = seção vinda de Collection (estática).
    - ``dynamic_ref`` populado = seção vinda de resolver dinâmico
      (``Destaques``, ``Recém saídos do forno``, etc.).
    - ``ref`` (sempre presente) identifica a seção no scroll-spy e na pill.
    """

    category: CategoryProjection | None
    items: tuple[CatalogItemProjection, ...]
    ref: str = ""
    label: str = ""
    icon: str = ""
    description: str = ""
    is_dynamic: bool = False
    dynamic_ref: str | None = None


@dataclass(frozen=True)
class CatalogProjection:
    """Top-level read model for the storefront menu."""

    items: tuple[CatalogItemProjection, ...]
    categories: tuple[CategoryProjection, ...]
    sections: tuple[CatalogSectionProjection, ...]
    featured: tuple[CatalogItemProjection, ...]
    active_category_ref: str | None
    happy_hour: HappyHourProjection | None = None
    favorite_category_ref: str | None = None
    has_items: bool = field(init=False)

    def __post_init__(self) -> None:
        # Dataclass is frozen; use object.__setattr__ for the derived flag.
        object.__setattr__(self, "has_items", bool(self.items))


# ──────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────


def build_catalog(
    *,
    channel_ref: str,
    collection_ref: str | None = None,
    request: HttpRequest | None = None,
) -> CatalogProjection:
    """Build a ``CatalogProjection`` for the given channel.

    - ``channel_ref`` is the listing ref AND the availability scope (storefront
      convention: Channel.ref == Listing.ref). No silent fallback: if the
      channel has no active listing, products filtered by listing simply
      won't appear, and tests must seed a Listing via fixture.
    - ``collection_ref`` filters to a single collection (category page).
    - ``request`` is optional; when provided, it derives session pricing
      hints (fulfillment type + subtotal) so prices shown on the menu match
      what the checkout will apply.
    """
    from shopman.storefront.omotenashi.context import OmotenashiContext

    config = ChannelConfig.for_channel(channel_ref)
    low_stock_threshold = Decimal(str(config.stock.low_stock_threshold))
    favorite_category_ref: str | None = OmotenashiContext.from_request(request).favorite_category

    categories = _build_categories()

    active_collection: Collection | None = None
    if collection_ref:
        active_collection = Collection.objects.filter(
            ref=collection_ref, is_active=True,
        ).first()

    products_by_collection = _fetch_products_by_collection(
        listing_ref=channel_ref,
        active_collection=active_collection,
    )

    popular = popular_skus(limit=5)
    ft_hint, sub_hint = session_pricing_hints(request)
    qty_in_cart_by_sku = _cart_qty_by_sku(request)

    # Flatten once for batching; remember grouping for sections.
    all_products: list[Product] = []
    group_index: list[tuple[str | None, int, int]] = []  # (collection_ref, start, end)
    for col_ref, products in products_by_collection:
        start = len(all_products)
        all_products.extend(products)
        group_index.append((col_ref, start, len(all_products)))

    if not all_products:
        return CatalogProjection(
            items=(),
            categories=categories,
            sections=(),
            featured=(),
            active_category_ref=collection_ref if active_collection else None,
            happy_hour=_happy_hour_projection(happy_hour_state()),
            favorite_category_ref=favorite_category_ref,
        )

    items_flat = _build_items(
        all_products,
        channel_ref=channel_ref,
        popular=popular,
        session_total_q=sub_hint,
        fulfillment_type=ft_hint,
        low_stock_threshold=low_stock_threshold,
        qty_in_cart_by_sku=qty_in_cart_by_sku,
    )

    static_sections = _build_sections(items_flat, group_index, categories)
    # Dinâmicas só em visão full (sem filtro de coleção específica)
    if active_collection is None:
        items_by_sku = {item.sku: item for item in items_flat}
        dynamic_sections = _build_dynamic_sections(channel_ref, items_by_sku)
        sections = dynamic_sections + static_sections
    else:
        sections = static_sections
    featured = tuple(item for item in items_flat if item.is_featured)

    return CatalogProjection(
        items=tuple(items_flat),
        categories=categories,
        sections=sections,
        featured=featured,
        active_category_ref=collection_ref if active_collection else None,
        happy_hour=_happy_hour_projection(happy_hour_state()),
        favorite_category_ref=favorite_category_ref,
    )


# ──────────────────────────────────────────────────────────────────────
# Internals — kept private; contract lives in build_catalog.
# ──────────────────────────────────────────────────────────────────────


def _build_categories() -> tuple[CategoryProjection, ...]:
    collections = Collection.objects.filter(is_active=True).order_by("sort_order", "name")
    result: list[CategoryProjection] = []
    for col in collections:
        try:
            url = reverse("storefront:menu_collection", args=[col.ref])
        except NoReverseMatch:
            url = f"/menu/{col.ref}/"
        result.append(
            CategoryProjection(
                ref=col.ref,
                name=col.name,
                icon=collection_icon(col.ref),
                url=url,
            ),
        )
    return tuple(result)


def _fetch_products_by_collection(
    *,
    listing_ref: str,
    active_collection: Collection | None,
) -> list[tuple[str | None, list[Product]]]:
    """Return an ordered list of (collection_ref | None, products).

    Products MUST have an active ``ListingItem`` on the channel's listing.
    No fallback: missing Listing → empty result (caller's problem to seed it).
    """
    base = Product.objects.filter(
        is_published=True,
        listing_items__listing__ref=listing_ref,
        listing_items__listing__is_active=True,
        listing_items__is_published=True,
    )

    if active_collection is not None:
        products = list(
            base.filter(collection_items__collection=active_collection)
            .order_by("collection_items__sort_order", "name")
            .distinct()
        )
        return [(active_collection.ref, products)]

    groups: list[tuple[str | None, list[Product]]] = []
    for col in Collection.objects.filter(is_active=True).order_by("sort_order", "name"):
        products = list(
            base.filter(collection_items__collection=col)
            .order_by("collection_items__sort_order", "name")
            .distinct()
        )
        if products:
            groups.append((col.ref, products))

    uncategorized = list(
        base.exclude(collection_items__isnull=False).order_by("name").distinct()
    )
    if uncategorized:
        groups.append((None, uncategorized))
    return groups


def build_catalog_items_for_skus(
    skus: list[str],
    *,
    channel_ref: str,
    request: HttpRequest | None = None,
) -> tuple[CatalogItemProjection, ...]:
    """Build ``CatalogItemProjection``s for an ad-hoc list of SKUs.

    Consumed by sibling projections (PDP substitutes / cross-sell cards)
    that need the same card shape as the menu but for an explicit SKU set
    rather than a collection section. Preserves the caller's SKU order,
    silently drops SKUs whose ``Product`` is missing or unpublished.
    """
    if not skus:
        return ()

    products_by_sku = {
        p.sku: p
        for p in Product.objects.filter(sku__in=skus, is_published=True)
    }
    ordered = [products_by_sku[sku] for sku in skus if sku in products_by_sku]
    if not ordered:
        return ()

    config = ChannelConfig.for_channel(channel_ref)
    low_stock_threshold = Decimal(str(config.stock.low_stock_threshold))
    popular = popular_skus(limit=5)
    ft_hint, sub_hint = session_pricing_hints(request)
    qty_in_cart_by_sku = _cart_qty_by_sku(request)

    return tuple(
        _build_items(
            ordered,
            channel_ref=channel_ref,
            popular=popular,
            session_total_q=sub_hint,
            fulfillment_type=ft_hint,
            low_stock_threshold=low_stock_threshold,
            qty_in_cart_by_sku=qty_in_cart_by_sku,
        )
    )


def _build_items(
    products: list[Product],
    *,
    channel_ref: str,
    popular: set[str],
    session_total_q: int,
    fulfillment_type: str,
    low_stock_threshold: Decimal,
    qty_in_cart_by_sku: dict[str, int] | None = None,
) -> list[CatalogItemProjection]:
    qty_in_cart_by_sku = qty_in_cart_by_sku or {}
    skus = [p.sku for p in products]

    # Batch: primary collection per SKU (used as `category` and for pricing context).
    sku_collections: dict[str, list[str]] = {}
    for ci in CollectionItem.objects.filter(product__sku__in=skus).select_related("collection"):
        sku_collections.setdefault(ci.product.sku, []).append(ci.collection.ref)

    # Batch: listing prices.
    price_map: dict[str, int] = {}
    for item in (
        ListingItem.objects.filter(
            listing__ref=channel_ref,
            listing__is_active=True,
            product__sku__in=skus,
            is_published=True,
            is_sellable=True,
        )
        .select_related("product")
        .order_by("-min_qty")
    ):
        price_map.setdefault(item.product.sku, item.price_q)

    # Batch: availability for the storefront scope.
    avail_map = _batch_availability(skus, channel_ref)

    result: list[CatalogItemProjection] = []
    for p in products:
        base_q = price_map.get(p.sku) or p.base_price_q

        cols = sku_collections.get(p.sku, [])
        price = CatalogService.get_price(
            p.sku,
            qty=1,
            listing=channel_ref,
            context={
                "sku_collections": cols,
                "session_total_q": session_total_q,
                "fulfillment_type": fulfillment_type,
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

        raw_avail = avail_map.get(p.sku)
        availability = _resolve_availability(
            raw_avail,
            p,
            low_stock_threshold=low_stock_threshold,
        )
        avail_label = AVAILABILITY_LABELS_PT[availability]
        can_add = availability in (
            Availability.AVAILABLE,
            Availability.LOW_STOCK,
            Availability.PLANNED_OK,
        )
        available_qty: int | None = None
        if raw_avail is not None and not raw_avail.get("is_paused", False):
            policy = raw_avail.get("availability_policy", "planned_ok")
            if policy != "demand_ok":
                total = raw_avail.get("total_promisable")
                if total is not None:
                    try:
                        available_qty = int(Decimal(str(total)))
                    except (TypeError, ValueError):
                        available_qty = None

        meta = p.metadata if isinstance(p.metadata, dict) else {}
        dietary = meta.get("dietary_info") or []
        if not isinstance(dietary, list):
            dietary = []
        allergens_raw = meta.get("allergens") or []
        allergens = tuple(str(a) for a in allergens_raw if a) if isinstance(allergens_raw, list) else ()

        result.append(
            CatalogItemProjection(
                sku=p.sku,
                slug=p.sku,  # storefront URL keys on SKU today
                name=p.name,
                short_description=p.short_description or "",
                image_url=p.image_url or None,
                category=cols[0] if cols else None,
                tags=_product_tags(p),
                base_price_q=int(effective_q or 0),
                price_display=_money(effective_q) if effective_q else "",
                has_promotion=has_promo,
                original_price_display=original_price_display,
                promotion_label=promotion_label,
                availability=availability,
                availability_label=avail_label,
                can_add_to_cart=can_add,
                available_qty=available_qty,
                dietary_info=tuple(str(d) for d in dietary),
                is_new=bool(meta.get("is_new", False)),
                is_featured=p.sku in popular,
                qty_in_cart=int(qty_in_cart_by_sku.get(p.sku, 0)),
                allergens=allergens,
            ),
        )
    return result


def _batch_availability(skus: list[str], channel_ref: str) -> dict[str, dict | None]:
    """Wrapper around ``stockman.availability_for_skus`` that stays silent
    when stockman isn't wired up (keeps projections callable in minimal envs).
    """
    try:
        from shopman.stockman.services.availability import availability_for_skus
    except ImportError:
        return {}

    try:
        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref)
        return availability_for_skus(
            skus,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
    except Exception as e:
        logger.warning("batch_availability_failed: %s", e, exc_info=True)
        return {}


def _build_sections(
    items_flat: list[CatalogItemProjection],
    group_index: list[tuple[str | None, int, int]],
    categories: tuple[CategoryProjection, ...],
) -> tuple[CatalogSectionProjection, ...]:
    category_by_ref = {c.ref: c for c in categories}
    sections: list[CatalogSectionProjection] = []
    for col_ref, start, end in group_index:
        slice_items = tuple(items_flat[start:end])
        if not slice_items:
            continue
        category = category_by_ref.get(col_ref) if col_ref else None
        sections.append(
            CatalogSectionProjection(
                category=category,
                items=slice_items,
                ref=category.ref if category else "outros",
                label=category.name if category else "Outros",
                icon=category.icon if category else "restaurant_menu",
            )
        )
    return tuple(sections)


def _build_dynamic_sections(
    channel_ref: str,
    items_by_sku: dict[str, CatalogItemProjection],
) -> tuple[CatalogSectionProjection, ...]:
    """Resolve dinâmicas configuradas em Shop.defaults['menu']['dynamic_collections']."""
    from shopman.shop import dynamic_collections as dyn
    from shopman.shop.models import Shop

    shop = Shop.load()
    menu_cfg = (shop.defaults or {}).get("menu", {}) if shop else {}
    dyn_refs = menu_cfg.get("dynamic_collections") or []
    if not isinstance(dyn_refs, list) or not dyn_refs:
        return ()

    sections: list[CatalogSectionProjection] = []
    for ref in dyn_refs:
        section = dyn.resolve(ref, channel_ref=channel_ref)
        if section is None:
            continue
        # Reusa CatalogItemProjection já construídos (mesmo pricing/availability)
        proj_items = tuple(
            items_by_sku[p.sku] for p in section.products if p.sku in items_by_sku
        )
        if not proj_items:
            continue
        sections.append(
            CatalogSectionProjection(
                category=None,
                items=proj_items,
                ref=section.meta.ref,
                label=section.meta.label,
                icon=section.meta.icon,
                description=section.meta.description,
                is_dynamic=True,
                dynamic_ref=section.meta.ref,
            )
        )
    return tuple(sections)


def _resolve_availability(
    raw_avail: dict | None,
    product: Product,
    *,
    low_stock_threshold: Decimal,
) -> Availability:
    """Map raw stock breakdown + product flags to the canonical enum.

    Precedence:
    1. Product not sellable → UNAVAILABLE
    2. No stockman data → AVAILABLE (trust product flag)
    3. Paused → UNAVAILABLE
    4. ``demand_ok`` policy → AVAILABLE
    5. No physical stock + ``planned_ok`` + is_planned → PLANNED_OK
    6. No physical stock otherwise → UNAVAILABLE
    7. 0 < promisable ≤ threshold → LOW_STOCK
    8. Otherwise → AVAILABLE
    """
    if not product.is_sellable:
        return Availability.UNAVAILABLE
    if raw_avail is None:
        return Availability.AVAILABLE

    if raw_avail.get("is_paused", False):
        return Availability.UNAVAILABLE

    policy = raw_avail.get("availability_policy", "planned_ok")
    if policy == "demand_ok":
        return Availability.AVAILABLE

    total_promisable = raw_avail.get("total_promisable", Decimal("0")) or Decimal("0")
    if not isinstance(total_promisable, Decimal):
        total_promisable = Decimal(str(total_promisable))

    if total_promisable <= 0:
        if policy == "planned_ok" and raw_avail.get("is_planned", False):
            return Availability.PLANNED_OK
        return Availability.UNAVAILABLE

    if total_promisable <= low_stock_threshold:
        return Availability.LOW_STOCK

    return Availability.AVAILABLE


def _product_tags(product: Product) -> tuple[str, ...]:
    """Read keywords (django-taggit) defensively — tests often skip tagging."""
    try:
        return tuple(t.name for t in product.keywords.all())
    except Exception:  # pragma: no cover — taggit may be unconfigured
        return ()


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


def _cart_qty_by_sku(request: HttpRequest | None) -> dict[str, int]:
    """Map ``sku → current qty`` for the visitor's open cart.

    Returns an empty dict when there is no request or no active session —
    the stepper then falls back to the "Adicionar" state.
    """
    if request is None:
        return {}
    try:
        from shopman.storefront.cart import CartService
    except ImportError:
        return {}
    try:
        cart = CartService.get_cart(request)
    except Exception:
        logger.warning("cart_qty_lookup_failed", exc_info=True)
        return {}
    result: dict[str, int] = {}
    for item in cart.get("items") or []:
        sku = item.get("sku")
        if not sku:
            continue
        try:
            result[sku] = int(Decimal(str(item.get("qty", 0) or 0)))
        except (ValueError, ArithmeticError):
            continue
    return result


def _happy_hour_projection(raw: dict) -> HappyHourProjection | None:
    if not raw or not raw.get("active"):
        return None
    return HappyHourProjection(
        active=True,
        discount_percent=int(raw.get("discount_percent", 0) or 0),
        start=str(raw.get("start", "")),
        end=str(raw.get("end", "")),
    )
