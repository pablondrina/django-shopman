"""HomeProjection — typed projection for the storefront home page.

Bundles everything the institutional home needs: omotenashi context (greeting,
moment, birthday flag), last-order quick-reorder hook, shop branding, shop
status, opening hours, and a small set of featured items for "Direto do Forno".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.http import HttpRequest

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.projections.catalog import CatalogItemProjection, build_catalog
from shopman.storefront.projections.shop import ShopProjection, build_shop_projection
from shopman.storefront.projections.shop_status import _format_opening_hours, _shop_status

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OmotenashiProjection:
    moment: str
    greeting: str
    greeting_with_name: str
    shop_hint: str
    customer_name: str | None
    is_birthday: bool
    audience: str
    is_open: bool
    opens_at: str | None
    closes_at: str | None


@dataclass(frozen=True)
class OpeningHoursEntry:
    label: str
    hours: str


@dataclass(frozen=True)
class ShopStatusProjection:
    is_open: bool
    message: str | None


@dataclass(frozen=True)
class CopyEntryProjection:
    title: str
    message: str


@dataclass(frozen=True)
class HomeHeroCopyProjection:
    birthday_heading: CopyEntryProjection
    birthday_sub: CopyEntryProjection
    order_title_prefix: CopyEntryProjection
    order_title_suffix: CopyEntryProjection
    order_subtitle: CopyEntryProjection
    reorder_title_prefix: CopyEntryProjection
    reorder_title_suffix: CopyEntryProjection
    reorder_subtitle: CopyEntryProjection
    handmade_title_prefix: CopyEntryProjection
    handmade_title_suffix: CopyEntryProjection
    handmade_subtitle: CopyEntryProjection
    menu_cta: CopyEntryProjection
    birthday_cta: CopyEntryProjection


@dataclass(frozen=True)
class LastOrderItemProjection:
    sku: str
    name: str
    qty: int


@dataclass(frozen=True)
class PublicConfigProjection:
    google_maps_api_key: str
    whatsapp_url: str


@dataclass(frozen=True)
class HomeProjection:
    omotenashi: OmotenashiProjection
    hero_copy: HomeHeroCopyProjection
    shop: ShopProjection
    shop_status: ShopStatusProjection
    opening_hours: tuple[OpeningHoursEntry, ...]
    last_order_ref: str | None
    last_order_items: tuple[LastOrderItemProjection, ...]
    featured_items: tuple[CatalogItemProjection, ...]
    origin_channel: str | None
    public_config: PublicConfigProjection


def build_home(request: HttpRequest) -> HomeProjection:
    from shopman.shop.models import Shop
    from shopman.shop.omotenashi import OmotenashiContext

    omo = OmotenashiContext.from_request(request)
    omotenashi = OmotenashiProjection(
        moment=omo.moment,
        greeting=omo.greeting,
        greeting_with_name=omo.greeting_with_name,
        shop_hint=omo.shop_hint,
        customer_name=omo.customer_name,
        is_birthday=omo.is_birthday,
        audience=omo.audience,
        is_open=omo.is_open,
        opens_at=omo.opens_at,
        closes_at=omo.closes_at,
    )

    shop = Shop.load()
    shop_proj = build_shop_projection(shop) if shop else _empty_shop()

    status_dict = _shop_status()
    shop_status = ShopStatusProjection(
        is_open=bool(status_dict.get("is_open", False)),
        message=status_dict.get("message"),
    )

    hours = tuple(
        OpeningHoursEntry(label=entry["label"], hours=entry["hours"])
        for entry in _format_opening_hours()
    )

    last_ref, last_items = _reorder_context(request)

    catalog = build_catalog(channel_ref=STOREFRONT_CHANNEL_REF, request=request)
    featured = tuple((catalog.featured or catalog.items)[:3])

    origin_channel = None
    try:
        session = getattr(request, "session", None)
        if session is not None:
            origin_channel = session.get("origin_channel")
    except Exception:
        logger.debug("home.origin_channel_unavailable", exc_info=True)
        origin_channel = None

    from django.conf import settings

    public_config = PublicConfigProjection(
        google_maps_api_key=getattr(settings, "GOOGLE_MAPS_API_KEY", "") or "",
        whatsapp_url=shop_proj.whatsapp_url or "",
    )

    return HomeProjection(
        omotenashi=omotenashi,
        hero_copy=_home_hero_copy(omotenashi),
        shop=shop_proj,
        shop_status=shop_status,
        opening_hours=hours,
        last_order_ref=last_ref,
        last_order_items=last_items,
        featured_items=featured,
        origin_channel=origin_channel,
        public_config=public_config,
    )


def _home_hero_copy(omotenashi: OmotenashiProjection) -> HomeHeroCopyProjection:
    return HomeHeroCopyProjection(
        birthday_heading=_copy_entry("BIRTHDAY_HERO_HEADING", omotenashi=omotenashi),
        birthday_sub=_copy_entry("BIRTHDAY_HERO_SUB", omotenashi=omotenashi),
        order_title_prefix=_copy_entry("HOME_HERO_ORDER_TITLE_PREFIX", omotenashi=omotenashi),
        order_title_suffix=_copy_entry("HOME_HERO_ORDER_TITLE_SUFFIX", omotenashi=omotenashi),
        order_subtitle=_copy_entry("HOME_HERO_ORDER_SUBTITLE", omotenashi=omotenashi),
        reorder_title_prefix=_copy_entry("HOME_HERO_REORDER_TITLE_PREFIX", omotenashi=omotenashi),
        reorder_title_suffix=_copy_entry("HOME_HERO_REORDER_TITLE_SUFFIX", omotenashi=omotenashi),
        reorder_subtitle=_copy_entry("HOME_HERO_REORDER_SUBTITLE", omotenashi=omotenashi),
        handmade_title_prefix=_copy_entry("HOME_HERO_HANDMADE_TITLE_PREFIX", omotenashi=omotenashi),
        handmade_title_suffix=_copy_entry("HOME_HERO_HANDMADE_TITLE_SUFFIX", omotenashi=omotenashi),
        handmade_subtitle=_copy_entry("HOME_HERO_HANDMADE_SUBTITLE", omotenashi=omotenashi),
        menu_cta=_copy_entry("HOME_MENU_CTA", omotenashi=omotenashi),
        birthday_cta=_copy_entry("HOME_BIRTHDAY_CTA", omotenashi=omotenashi),
    )


def _copy_entry(key: str, *, omotenashi: OmotenashiProjection) -> CopyEntryProjection:
    from shopman.shop.omotenashi import resolve_copy

    entry = resolve_copy(key, moment=omotenashi.moment, audience=omotenashi.audience)
    return CopyEntryProjection(title=entry.title, message=entry.message)


def _reorder_context(request: HttpRequest) -> tuple[str | None, tuple[LastOrderItemProjection, ...]]:
    customer_info = getattr(request, "customer", None)
    if customer_info is None:
        return None, ()
    try:
        from shopman.storefront.services import orders as order_service

        ref, items = order_service.last_reorder_context(
            customer_uuid=customer_info.uuid,
            min_days=0,
        )
        projections = tuple(
            LastOrderItemProjection(
                sku=str(item.get("sku", "")),
                name=str(item.get("name", "")),
                qty=int(item.get("qty", 1) or 1),
            )
            for item in items
            if item.get("sku")
        )
        return ref, projections
    except Exception:
        logger.debug("home.reorder_context_failed", exc_info=True)
        return None, ()


def _empty_shop() -> ShopProjection:
    return ShopProjection(
        brand_name="",
        tagline="",
        description="",
        description_html="",
        logo_name="",
        logo_url="",
        color_mode="auto",
        theme_color="",
        background_color="",
        design_tokens={},
        whatsapp_url="",
        phone="",
        phone_display="",
        phone_url="",
        email="",
        full_address="",
        maps_url="",
        default_city="",
        social_links=(),
    )
