"""CatalogProjection — immutable UI projection for the storefront menu/catalog.

Phase 1 pilot of the PROJECTION-UI-PLAN. The builder orchestrates shop
services for catalog/price/availability plus ``services.storefront_context``
for session/happy-hour/popularity, and emits a frozen, immutable shape the
templates consume without ever touching Django model instances.

The projection never imports from ``shopman.storefront.views.*`` — everything it
needs lives under ``services`` or in sibling projection modules. Business
rules like the low-stock threshold come from ``ChannelConfig`` so they're
Admin-configurable per channel.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from shopman.utils.monetary import format_money

from shopman.shop.config import ChannelConfig
from shopman.shop.projections import catalog_context
from shopman.shop.projections.storefront_context import (
    happy_hour_state,
    popular_skus,
    session_pricing_hints,
)
from shopman.shop.projections.types import (
    Availability,
    CategoryProjection,
    HappyHourProjection,
)
from shopman.storefront.presentation.dietary import dietary_warnings as _dietary_warnings
from shopman.storefront.presentation.icons import collection_icon
from shopman.storefront.presentation.status import availability_label

if TYPE_CHECKING:
    from django.http import HttpRequest  # noqa: F401

logger = logging.getLogger(__name__)


def get_channel_listing_ref() -> str | None:
    """Ref of the storefront channel's listing — by convention, the channel ref.

    Storefront-bound resolver: callers feed the result to the surface-agnostic
    ``catalog_context`` facades (``price_q_for_product``, listing filters).
    """
    from shopman.shop.models import Channel

    from ..constants import STOREFRONT_CHANNEL_REF

    try:
        channel = Channel.objects.filter(ref=STOREFRONT_CHANNEL_REF).first()
        return channel.ref if channel else None
    except Exception as exc:
        logger.warning("channel_listing_ref_failed: %s", exc, exc_info=True)
        return None


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
    search_terms: tuple[str, ...]

    # Price (dual: raw + display)
    base_price_q: int
    price_display: str
    has_promotion: bool
    original_price_display: str | None
    promotion_label: str | None
    unit_weight_label: str | None

    # Availability (canonical enum + pt-BR label)
    availability: Availability
    availability_label: str
    can_add_to_cart: bool

    # Dietary / attributes
    dietary_info: tuple[str, ...]
    is_new: bool
    is_featured: bool

    # Cart state (populated when the builder receives a request)
    qty_in_cart: int = 0

    # Disponibilidade — distingue, dentro de UNAVAILABLE, "pausado pelo operador"
    # de "esgotado de verdade". `is_notifiable` = esgotado honesto (vendável, não
    # pausado, sem plano) → habilita o CTA "Me avise quando disponível" (WP-3).
    # Pausado NÃO é notificável (decisão do operador, não falta de estoque).
    is_paused: bool = False
    is_notifiable: bool = False

    # "Me avise" já assinado por este viewer (cliente logado por customer_ref, ou
    # anônimo via sessão). PERSISTE o estado do sino entre reloads. Só faz sentido
    # quando is_notifiable; False caso contrário.
    is_notify_subscribed: bool = False

    # Estado do coração (favorito do cliente logado). Populado quando o builder
    # recebe um request autenticado; False p/ anônimo.
    is_favorite: bool = False

    # Avisos de preferência alimentar (ex.: "Contém glúten") quando o produto
    # conflita com uma preferência ATIVA do cliente logado. Vazio p/ anônimo ou
    # sem conflito (omotenashi: avisar, nunca esconder).
    dietary_warnings: tuple[str, ...] = field(default_factory=tuple)

    # Available quantity for stock-aware UX. None = demand-based/untracked
    # (sem teto). Integer = exato. Permite o menu abrir o modal de estoque
    # client-side quando requested > available, sem esperar o POST falhar.
    available_qty: int | None = None

    # Allergens from product.metadata["allergens"] — search/index data only.
    allergens: tuple[str, ...] = field(default_factory=tuple)


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
    """Top-level projection for the storefront menu."""

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
    from shopman.shop.omotenashi.context import OmotenashiContext

    config = ChannelConfig.for_channel(channel_ref)
    low_stock_threshold = Decimal(str(config.stock.low_stock_threshold))
    favorite_category_ref: str | None = OmotenashiContext.from_request(request).favorite_category

    categories = _build_categories()

    active_collection: Any | None = None
    if collection_ref:
        active_collection = catalog_context.get_active_collection(collection_ref)

    products_by_collection = _fetch_products_by_collection(
        listing_ref=channel_ref,
        active_collection=active_collection,
    )

    popular = popular_skus(limit=5)
    ft_hint, sub_hint = session_pricing_hints(request)
    qty_in_cart_by_sku = _cart_qty_by_sku(request)

    # Flatten once for batching; remember grouping for sections.
    all_products: list[Any] = []
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
        favorite_skus=_favorite_skus(request),
        subscribed_skus=_notify_subscribed_skus(request),
        active_food_prefs=_active_food_prefs(request),
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
    result: list[CategoryProjection] = []
    for col in catalog_context.active_collections():
        result.append(
            CategoryProjection(
                ref=col.ref,
                name=col.name,
                icon=collection_icon(col.ref),
                url=_menu_anchor_url(col.ref),
            ),
        )
    return tuple(result)


def _fetch_products_by_collection(
    *,
    listing_ref: str,
    active_collection: Any | None,
) -> list[tuple[str | None, list[Any]]]:
    """Return an ordered list of (collection_ref | None, products).

    Products MUST have an active ``ListingItem`` on the channel's listing.
    No fallback: missing Listing → empty result (caller's problem to seed it).
    """
    return catalog_context.published_products_by_collection(
        listing_ref=listing_ref,
        active_collection=active_collection,
    )


def build_catalog_items_for_skus(
    skus: list[str],
    *,
    channel_ref: str,
    request: HttpRequest | None = None,
) -> tuple[CatalogItemProjection, ...]:
    """Build ``CatalogItemProjection``s for an ad-hoc list of SKUs.

    Consumed by sibling surfaces (PDP substitutes / cross-sell cards, the home
    "Direto do Forno" rail) that need the same card shape as the menu but for an
    explicit SKU set rather than a collection section. Preserves the caller's
    SKU order, silently drops SKUs whose ``Product`` is missing or unpublished.
    """
    if not skus:
        return ()

    products_by_sku = catalog_context.products_by_sku(skus, only_published=True)
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
            favorite_skus=_favorite_skus(request),
            subscribed_skus=_notify_subscribed_skus(request),
            active_food_prefs=_active_food_prefs(request),
        )
    )


def _build_items(
    products: list[Any],
    *,
    channel_ref: str,
    popular: set[str],
    session_total_q: int,
    fulfillment_type: str,
    low_stock_threshold: Decimal,
    qty_in_cart_by_sku: dict[str, int] | None = None,
    favorite_skus: set[str] | None = None,
    subscribed_skus: set[str] | None = None,
    active_food_prefs=frozenset(),
) -> list[CatalogItemProjection]:
    qty_in_cart_by_sku = qty_in_cart_by_sku or {}
    favorite_skus = favorite_skus or set()
    subscribed_skus = subscribed_skus or set()
    skus = [p.sku for p in products]

    # Batch: collections per SKU (used as `category` and for pricing context).
    sku_collections = catalog_context.collection_refs_by_sku(skus)

    # Batch: listing prices.
    price_map = catalog_context.listing_price_map(skus, channel_ref)

    # Batch: availability for the storefront scope.
    avail_map = _batch_availability(skus, channel_ref)

    # Bundles nao tem quant proprio: sua disponibilidade e o min() dos
    # componentes (o mais escasso limita), senao o card mostraria "Disponivel"
    # com um componente esgotado. Sobrescreve o raw do bundle antes de resolver.
    bundle_skus = [p.sku for p in products if getattr(p, "is_bundle", False)]
    if bundle_skus:
        avail_map.update(
            catalog_context.bundle_availability_for_skus(bundle_skus, channel_ref=channel_ref)
        )

    result: list[CatalogItemProjection] = []
    for p in products:
        base_q = price_map.get(p.sku) or p.base_price_q

        cols = sku_collections.get(p.sku, [])
        price = catalog_context.contextual_price(
            p.sku,
            qty=1,
            listing_ref=channel_ref,
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
            is_sellable=p.is_sellable,
            low_stock_threshold=low_stock_threshold,
        )
        avail_label = availability_label(availability)
        can_add = availability in (
            Availability.AVAILABLE,
            Availability.LOW_STOCK,
            Availability.PLANNED_OK,
        )
        # Pausado = decisão do operador: produto publicado (aparece no cardápio)
        # mas não vendável, ou stock marcado como pausado. Distingue-se do esgotado
        # honesto (que habilita "Me avise"). Espelha catalog_context (`or not is_sellable`).
        is_paused = (not p.is_sellable) or bool(raw_avail and raw_avail.get("is_paused"))
        is_notifiable = (
            availability == Availability.UNAVAILABLE and p.is_sellable and not is_paused
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
        tags = _product_tags(p)

        result.append(
            CatalogItemProjection(
                sku=p.sku,
                slug=p.sku,  # storefront URL keys on SKU today
                name=p.name,
                short_description=p.short_description or "",
                image_url=p.image_url or None,
                category=cols[0] if cols else None,
                tags=tags,
                search_terms=_search_terms(
                    p,
                    tags=tags,
                    allergens=allergens,
                    dietary=tuple(str(d) for d in dietary),
                ),
                base_price_q=int(effective_q or 0),
                price_display=_money(effective_q) if effective_q else "",
                has_promotion=has_promo,
                original_price_display=original_price_display,
                promotion_label=promotion_label,
                unit_weight_label=_unit_weight_label(p),
                availability=availability,
                availability_label=avail_label,
                can_add_to_cart=can_add,
                is_paused=is_paused,
                is_notifiable=is_notifiable,
                is_notify_subscribed=is_notifiable and p.sku in subscribed_skus,
                available_qty=available_qty,
                dietary_info=tuple(str(d) for d in dietary),
                is_new=bool(meta.get("is_new", False)),
                is_featured=p.sku in popular,
                qty_in_cart=int(qty_in_cart_by_sku.get(p.sku, 0)),
                is_favorite=p.sku in favorite_skus,
                dietary_warnings=_dietary_warnings(
                    active_food_prefs, dietary_info=dietary, allergens=allergens
                ),
                allergens=allergens,
            ),
        )
    return result


def _batch_availability(skus: list[str], channel_ref: str) -> dict[str, dict | None]:
    """Wrapper around ``stockman.availability_for_skus`` that stays silent
    when stockman isn't wired up (keeps projections callable in minimal envs).
    """
    return catalog_context.availability_for_skus(skus, channel_ref=channel_ref)


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
    *,
    is_sellable: bool,
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
    resolved = catalog_context.basic_availability(
        raw_avail,
        is_sellable=is_sellable,
        low_stock_threshold=low_stock_threshold,
    )
    return Availability(resolved.status)


def _product_tags(product: Any) -> tuple[str, ...]:
    """Read keywords (django-taggit) defensively — tests often skip tagging."""
    return catalog_context.product_tags(product)


def _unit_weight_label(product: Any) -> str | None:
    return f"~{product.unit_weight_g}g a unidade" if getattr(product, "unit_weight_g", None) else None


def _search_terms(
    product: Any,
    *,
    tags: tuple[str, ...],
    allergens: tuple[str, ...],
    dietary: tuple[str, ...],
) -> tuple[str, ...]:
    """Build canonical menu-search terms from product PIM data."""
    values = [
        product.sku,
        product.name,
        product.short_description or "",
        product.long_description or "",
        product.ingredients_text or "",
        *tags,
        *allergens,
        *dietary,
    ]
    return tuple(str(value).strip() for value in values if str(value).strip())


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


def _menu_anchor_url(ref: str) -> str:
    return f"/menu#{ref}" if ref else "/menu"


def _favorite_skus(request: HttpRequest | None) -> set[str]:
    """SKUs the logged-in customer has favorited (empty for anonymous)."""
    if request is None:
        return set()
    try:
        from shopman.storefront.identity import get_authenticated_customer
        from shopman.storefront.services import favorites

        customer = get_authenticated_customer(request)
        if customer is None:
            return set()
        return favorites.favorite_sku_set(customer.ref)
    except Exception:
        logger.debug("catalog._favorite_skus failed", exc_info=True)
        return set()


def _notify_subscribed_skus(request: HttpRequest | None) -> set[str]:
    """SKUs com 'Me avise' já pedido por este viewer — persiste o estado do sino.

    Logado: por customer_ref/telefone da conta. Anônimo: SKUs gravados na sessão
    Django pelo endpoint de inscrição (mesma sessão que serve o cardápio).
    """
    if request is None:
        return set()
    try:
        from shopman.storefront.identity import get_authenticated_customer
        from shopman.storefront.services import stock_alerts

        skus: set[str] = set()
        customer = get_authenticated_customer(request)
        if customer is not None:
            skus |= stock_alerts.subscribed_skus(customer=customer)
        session = getattr(request, "session", None)
        session_skus = session.get("stock_alert_skus") if session is not None else None
        if isinstance(session_skus, (list, tuple, set)):
            skus |= {str(s) for s in session_skus}
        return skus
    except Exception:
        logger.debug("catalog._notify_subscribed_skus failed", exc_info=True)
        return set()


def _active_food_prefs(request: HttpRequest | None):
    """Active food-preference keys for the logged-in customer (empty otherwise)."""
    if request is None:
        return frozenset()
    try:
        from shopman.shop.projections import customer_context
        from shopman.storefront.identity import get_authenticated_customer

        customer = get_authenticated_customer(request)
        if customer is None:
            return frozenset()
        return customer_context.active_preference_keys(customer.ref, "alimentar")
    except Exception:
        logger.debug("catalog._active_food_prefs failed", exc_info=True)
        return frozenset()


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
        # Only sku→qty is needed here; the cheap summary avoids paying for
        # full availability/discount resolution on every menu render.
        cart = CartService.get_cart_summary(request, include_items=True)
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
