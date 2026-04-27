"""ProductDetailProjection — read model for the storefront PDP.

Phase 1 / step 2 of the PROJECTION-UI-PLAN. Mirrors the discipline of
``build_catalog``: the builder orchestrates shop services for pricing, bundle
expansion, availability, and session pricing, then emits a frozen, immutable
shape the PDP template consumes without ever touching Django model instances.

Substitutos NÃO pertencem à PDP (AVAILABILITY-PLAN §5) — só aparecem no
modal de erro de estoque. Por isso este projection não os carrega.

Never imports from ``shopman.storefront.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from shopman.utils.monetary import format_money

from shopman.shop.config import ChannelConfig
from shopman.shop.projections.types import (
    AVAILABILITY_LABELS_PT,
    Availability,
    CategoryProjection,
    ComponentProjection,
)
from shopman.shop.services import catalog_context
from shopman.shop.services.storefront_context import session_pricing_hints

from .catalog import (
    _cart_qty_by_sku,
    _resolve_availability,
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
class NutritionRowProjection:
    """One displayable row of the nutrition table.

    ``value_display`` is already formatted (``"12,5"``). ``unit`` is a
    short unit string (``"g"``, ``"mg"``, ``"kcal"``).
    ``percent_daily_value`` is the rounded %VD or ``None`` when the
    nutrient has no ANVISA reference value or the amount is zero.
    """

    field: str
    label: str
    value_display: str
    unit: str
    percent_daily_value: int | None


@dataclass(frozen=True)
class NutritionFactsProjection:
    """PDP-facing, pre-formatted nutrition table."""

    serving_size_display: str
    servings_per_container: int
    energy_kcal_display: str | None
    energy_pdv: int | None
    rows: tuple[NutritionRowProjection, ...]

    @property
    def has_any(self) -> bool:
        return bool(self.rows) or bool(self.energy_kcal_display)


@dataclass(frozen=True)
class ConservationInfoProjection:
    """Shelf life / storage guidance panel for a PDP.

    ``storage_tip`` is either the author's per-SKU override or the
    shop-wide default (resolved by ``_conservation``).
    """

    shelf_life_label: str | None
    storage_tip: str | None

    @property
    def has_any(self) -> bool:
        return bool(self.shelf_life_label or self.storage_tip)


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

    # Unit weight (spec próxima ao preço — "~250g a unidade")
    unit_weight_label: str | None
    approx_dimensions_label: str | None

    # Dietary / allergen
    allergen: AllergenInfoProjection | None

    # Conservation / freshness
    conservation: ConservationInfoProjection | None

    # Ingredients (human text, pt-BR) + nutritional table
    ingredients_text: str | None
    nutrition: NutritionFactsProjection | None

    # SEO/search-facing product facts
    seo_description: str
    seo_keywords: tuple[str, ...]

    # Breadcrumb
    breadcrumb_category: CategoryProjection | None


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

    Returns ``None`` when:
    - the product does not exist or is unpublished, OR
    - the product is not present in this channel's listing (no ``ListingItem``
      or the listing item is unpublished / not sellable). AVAILABILITY-PLAN §5
      folds "fora do canal" into 404 — coerência total: search não mostra,
      menu não lista, PDP via URL direta devolve 404.

    Callers convert ``None`` into a 404. Paused/sold-out remain projection
    state (the PDP renders with an "Indisponível" badge).
    """
    product = catalog_context.get_published_product(sku)
    if product is None:
        return None
    if not _sku_listed_in_channel(product, channel_ref):
        return None

    config = ChannelConfig.for_channel(channel_ref)
    low_stock_threshold = Decimal(str(config.stock.low_stock_threshold))

    base_q = catalog_context.listing_price_for_product(product, channel_ref) or product.base_price_q

    sku_collections = catalog_context.collection_refs_by_sku([product.sku]).get(product.sku, [])

    ft_hint, sub_hint = session_pricing_hints(request)
    price = catalog_context.contextual_price(
        product.sku,
        qty=1,
        listing_ref=channel_ref,
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
    # Session-aware: add the session's own hold back to the promisable qty
    # so the PDP matches the cart's view for the shopper themselves
    # (AVAILABILITY-PLAN §3 max_orderable formula).
    raw_avail = _availability(product.sku, channel_ref)
    session_key = _session_key(request)
    own_hold = int(
        _own_holds_service().own_holds_by_sku(session_key, [product.sku]).get(product.sku, 0)
    ) if session_key else 0
    raw_avail_session = catalog_context.availability_with_own_hold(raw_avail, own_hold)
    availability = _resolve_availability(
        raw_avail_session,
        is_sellable=product.is_sellable,
        low_stock_threshold=low_stock_threshold,
    )
    availability_label = AVAILABILITY_LABELS_PT[availability]
    can_add_to_cart = availability in (
        Availability.AVAILABLE,
        Availability.LOW_STOCK,
        Availability.PLANNED_OK,
    )
    available_qty = catalog_context.promisable_int(raw_avail_session)

    # Bundle components — expand only if the product declares itself a bundle.
    components = _components(product)

    allergen = _allergen(product)
    conservation = _conservation(product)
    ingredients_text = (product.ingredients_text or "").strip() or None
    nutrition = _nutrition(product)
    breadcrumb_category = _breadcrumb_category(product)
    seo_description = _seo_description(
        product,
        allergen=allergen,
        conservation=conservation,
    )
    seo_keywords = _seo_keywords(product, allergen=allergen)

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
        unit_weight_label=_unit_weight_label(product),
        approx_dimensions_label=_approx_dimensions_label(product),
        allergen=allergen,
        conservation=conservation,
        ingredients_text=ingredients_text,
        nutrition=nutrition,
        seo_description=seo_description,
        seo_keywords=seo_keywords,
        breadcrumb_category=breadcrumb_category,
    )


# ──────────────────────────────────────────────────────────────────────
# Internals
# ──────────────────────────────────────────────────────────────────────


def _availability(sku: str, channel_ref: str) -> dict | None:
    return catalog_context.availability_for_sku(sku, channel_ref=channel_ref)


def _sku_listed_in_channel(product: Any, channel_ref: str) -> bool:
    """Is this SKU available in the given channel's listing?

    Channels without a ``Listing`` configured fall through to ``True`` so
    internal/fallback channels (e.g. POS) keep working. Strict gating only
    applies when a Listing actually exists with the channel's ref.
    """
    return catalog_context.listed_in_channel(
        product,
        channel_ref,
        fallback_when_listing_missing=True,
    )


def _session_key(request) -> str:
    """Return the cart session key from the request, or empty string."""
    if request is None:
        return ""
    try:
        return request.session.get("cart_session_key") or ""
    except Exception:
        logger.debug("product_detail_projection_session_key_failed", exc_info=True)
        return ""


def _own_holds_service():
    """Lazy import of the availability service to avoid circular deps."""
    from shopman.shop.services import availability

    return availability


def _components(product: Any) -> tuple[ComponentProjection, ...]:
    if not product.is_bundle:
        return ()
    try:
        raw = catalog_context.expand_bundle(product.sku)
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


def _allergen(product: Any) -> AllergenInfoProjection | None:
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


def _seo_description(
    product: Any,
    *,
    allergen: AllergenInfoProjection | None,
    conservation: ConservationInfoProjection | None,
) -> str:
    parts = [
        product.short_description or product.long_description or product.name,
    ]
    if allergen and allergen.allergens:
        parts.append(f"Alérgenos: {', '.join(allergen.allergens)}.")
    if allergen and allergen.dietary_info:
        parts.append(f"Restrições: {', '.join(allergen.dietary_info)}.")
    if conservation and conservation.shelf_life_label:
        parts.append(conservation.shelf_life_label + ".")
    return " ".join(str(part).strip() for part in parts if str(part).strip())


def _seo_keywords(
    product: Any,
    *,
    allergen: AllergenInfoProjection | None,
) -> tuple[str, ...]:
    values = [
        product.name,
        product.sku,
        *catalog_context.product_tags(product),
    ]
    if allergen:
        values.extend(allergen.allergens)
        values.extend(allergen.dietary_info)
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            result.append(text)
    return tuple(result)


def _conservation(product: Any) -> ConservationInfoProjection | None:
    """Resolve conservation panel with per-SKU override → shop-wide default fallback."""
    shelf_life_label = _shelf_life_label(product.shelf_life_days)
    storage_tip = product.storage_tip.strip() if product.storage_tip else None
    if not storage_tip:
        try:
            from shopman.shop.models import Shop
            shop = Shop.load()
            default_tip = (shop.conservation_tips_default or "").strip() if shop else ""
            storage_tip = default_tip or None
        except Exception:
            logger.debug(
                "product_detail_projection_conservation_tip_failed sku=%s",
                product.sku,
                exc_info=True,
            )
    if not (shelf_life_label or storage_tip):
        return None
    return ConservationInfoProjection(
        shelf_life_label=shelf_life_label,
        storage_tip=storage_tip,
    )


def _unit_weight_label(product: Any) -> str | None:
    return f"~{product.unit_weight_g}g a unidade" if product.unit_weight_g else None


def _approx_dimensions_label(product: Any) -> str | None:
    meta = product.metadata if isinstance(product.metadata, dict) else {}
    raw = meta.get("approx_dimensions") or meta.get("dimensions")
    return str(raw).strip() if raw else None


# Units shown next to each nutrient in the PDP table.
_NUTRIENT_UNITS: dict[str, str] = {
    "carbohydrates_g": "g",
    "sugars_g": "g",
    "proteins_g": "g",
    "total_fat_g": "g",
    "saturated_fat_g": "g",
    "trans_fat_g": "g",
    "fiber_g": "g",
    "sodium_mg": "mg",
}

# Order in which rows are rendered on the PDP.
_NUTRIENT_ORDER: tuple[str, ...] = (
    "carbohydrates_g",
    "sugars_g",
    "proteins_g",
    "total_fat_g",
    "saturated_fat_g",
    "trans_fat_g",
    "fiber_g",
    "sodium_mg",
)


def _nutrient_pdp_label(field_name: str) -> str:
    """Return a PDP label without unit suffix; the value column owns units."""
    label = catalog_context.nutrient_label(field_name)
    return label.rsplit(" (", maxsplit=1)[0]


def _nutrition(product: Any) -> NutritionFactsProjection | None:
    """Build the PDP-facing nutrition projection from ``product.nutrition_facts``.

    Returns ``None`` when there's nothing to show.
    """
    facts = catalog_context.nutrition_facts(product)
    if facts is None or not facts.has_any_nutrient:
        return None

    rows: list[NutritionRowProjection] = []
    for field_name in _NUTRIENT_ORDER:
        value = getattr(facts, field_name)
        if value is None:
            continue
        rows.append(
            NutritionRowProjection(
                field=field_name,
                label=_nutrient_pdp_label(field_name),
                value_display=_format_number(value),
                unit=_NUTRIENT_UNITS[field_name],
                percent_daily_value=facts.percent_daily_value(field_name),
            )
        )

    serving_label = _format_serving(facts.serving_size_g)
    energy_display = (
        f"{int(round(facts.energy_kcal))}"
        if facts.energy_kcal is not None
        else None
    )
    energy_pdv = facts.percent_daily_value("energy_kcal")

    return NutritionFactsProjection(
        serving_size_display=serving_label,
        servings_per_container=facts.servings_per_container,
        energy_kcal_display=energy_display,
        energy_pdv=energy_pdv,
        rows=tuple(rows),
    )


def _format_number(value: float) -> str:
    """Render a nutrient amount with at most 1 decimal, comma as separator."""
    rounded = round(float(value), 1)
    if rounded == int(rounded):
        return str(int(rounded))
    return f"{rounded:.1f}".replace(".", ",")


def _format_serving(serving_size_g: int) -> str:
    if serving_size_g <= 0:
        return ""
    return f"{serving_size_g} g"


def _shelf_life_label(shelf_life_days: int | None) -> str | None:
    if shelf_life_days is None:
        return None
    if shelf_life_days == 0:
        return "Melhor consumido no mesmo dia"
    if shelf_life_days == 1:
        return "Melhor consumido em até 1 dia"
    return f"Conserva bem por {shelf_life_days} dias"


def _breadcrumb_category(product: Any) -> CategoryProjection | None:
    from django.urls import NoReverseMatch, reverse

    from shopman.storefront.projections.icons import collection_icon

    col = catalog_context.breadcrumb_collection(product)
    if col is None:
        return None
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


def _gallery(product: Any) -> tuple[str, ...]:
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


def _allergen_info(product: Any) -> dict | None:
    """Extract allergen and dietary info from product.metadata.

    Returns dict with keys: allergens (list), dietary_info (list), serves (str|None)
    or None if no info available.
    """
    meta = getattr(product, "metadata", None)
    if not meta or not isinstance(meta, dict):
        return None

    allergens = meta.get("allergens", [])
    dietary = meta.get("dietary_info", [])
    serves = meta.get("serves")

    if not allergens and not dietary and not serves:
        return None

    return {
        "allergens": allergens if isinstance(allergens, list) else [],
        "dietary_info": dietary if isinstance(dietary, list) else [],
        "serves": str(serves) if serves else None,
    }
