"""HomeProjection — typed projection for the storefront home page.

Bundles everything the institutional home needs: omotenashi context (greeting,
moment, birthday flag), last-order quick-reorder hook, shop branding, shop
status, opening hours, and a small set of featured items for "Direto do Forno".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.http import HttpRequest

from shopman.shop.projections.types import Action
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation.catalog import CatalogItemProjection, build_catalog
from shopman.storefront.presentation.shop import ShopProjection, build_shop_projection
from shopman.storefront.presentation.shop_status import _format_opening_hours, _shop_status

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


@dataclass(frozen=True)
class OpeningHoursEntry:
    label: str
    hours: str


@dataclass(frozen=True)
class ShopStatusProjection:
    is_open: bool
    label: str
    message: str | None
    opens_at: str | None
    closes_at: str | None


@dataclass(frozen=True)
class HomeNoticeProjection:
    ref: str
    tone: str
    title: str
    message: str
    priority: str
    actions: tuple[Action, ...] = ()


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
class HomeSectionsCopyProjection:
    availability_heading: CopyEntryProjection
    full_menu_cta: CopyEntryProjection
    how_it_works_heading: CopyEntryProjection
    how_it_works_intro: CopyEntryProjection
    how_online_heading: CopyEntryProjection
    how_store_heading: CopyEntryProjection
    how_step_choose: CopyEntryProjection
    how_step_pay: CopyEntryProjection
    how_step_fulfill: CopyEntryProjection
    how_self_service_label: CopyEntryProjection
    how_counter_label: CopyEntryProjection
    how_hours_label: CopyEntryProjection
    how_hours_empty: CopyEntryProjection
    how_online_choose_message: CopyEntryProjection
    how_online_pay_message: CopyEntryProjection
    how_online_track_message: CopyEntryProjection
    how_store_self_service_message: CopyEntryProjection
    how_store_counter_message: CopyEntryProjection
    tomorrow_label: CopyEntryProjection
    tomorrow_hook: CopyEntryProjection
    whatsapp_cta: CopyEntryProjection
    whatsapp_cta_label: CopyEntryProjection


@dataclass(frozen=True)
class AuthCopyProjection:
    phone_heading: CopyEntryProjection
    phone_subtitle: CopyEntryProjection
    phone_cta_wa: CopyEntryProjection
    phone_cta_sms: CopyEntryProjection
    trusted_device_message: CopyEntryProjection
    trusted_device_cta: CopyEntryProjection
    trusted_other_phone: CopyEntryProjection
    no_password_note: CopyEntryProjection
    terms_note: CopyEntryProjection
    code_heading: CopyEntryProjection
    code_help: CopyEntryProjection
    name_heading: CopyEntryProjection
    name_subtitle: CopyEntryProjection
    name_cta: CopyEntryProjection
    auth_confirmed: CopyEntryProjection
    device_trust_prompt: CopyEntryProjection
    device_trust_cta: CopyEntryProjection
    device_trust_skip_cta: CopyEntryProjection
    device_trust_redirecting: CopyEntryProjection
    device_trust_saved: CopyEntryProjection


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
    sections_copy: HomeSectionsCopyProjection
    auth_copy: AuthCopyProjection
    shop: ShopProjection
    shop_status: ShopStatusProjection
    notices: tuple[HomeNoticeProjection, ...]
    opening_hours: tuple[OpeningHoursEntry, ...]
    last_order_ref: str | None
    last_order_items: tuple[LastOrderItemProjection, ...]
    actions: tuple[Action, ...]
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
    )

    shop = Shop.load()
    shop_proj = build_shop_projection(shop) if shop else _empty_shop()

    status_dict = _shop_status()
    shop_status = ShopStatusProjection(
        is_open=bool(status_dict.get("is_open", False)),
        label=status_dict.get("label") or ("Aberto agora" if status_dict.get("is_open") else "Fechado agora"),
        message=status_dict.get("message"),
        opens_at=status_dict.get("opens_at"),
        closes_at=status_dict.get("closes_at"),
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

    notices = _home_notices(
        shop_status=shop_status,
        omotenashi=omotenashi,
        origin_channel=origin_channel,
        whatsapp_url=public_config.whatsapp_url,
    )

    return HomeProjection(
        omotenashi=omotenashi,
        hero_copy=_home_hero_copy(omotenashi),
        sections_copy=_home_sections_copy(omotenashi),
        auth_copy=_auth_copy(omotenashi),
        shop=shop_proj,
        shop_status=shop_status,
        notices=notices,
        opening_hours=hours,
        last_order_ref=last_ref,
        last_order_items=last_items,
        actions=_home_actions(last_ref),
        featured_items=featured,
        origin_channel=origin_channel,
        public_config=public_config,
    )


def _home_notices(
    *,
    shop_status: ShopStatusProjection,
    omotenashi: OmotenashiProjection,
    origin_channel: str | None,
    whatsapp_url: str,
) -> tuple[HomeNoticeProjection, ...]:
    notices: list[HomeNoticeProjection] = []

    status_message = (shop_status.message or "").strip()
    if status_message:
        if not shop_status.is_open:
            tone = "warning"
            title = "Loja fechada agora"
        elif omotenashi.moment == "fechando":
            tone = "warning"
            title = "Estamos perto do fechamento"
        else:
            tone = "info"
            title = "Status da loja"

        actions = [
            Action(
                ref="view_menu",
                kind="link",
                label="Ver cardápio",
                href="/menu",
                priority="secondary",
            )
        ]
        if whatsapp_url:
            actions.append(Action(
                ref="contact_whatsapp",
                kind="external",
                label="Falar no WhatsApp",
                href=whatsapp_url,
                priority="quiet",
            ))

        notices.append(HomeNoticeProjection(
            ref="shop_status",
            tone=tone,
            title=title,
            message=status_message,
            priority="global",
            actions=tuple(actions),
        ))

    if origin_channel == "whatsapp":
        notices.append(HomeNoticeProjection(
            ref="origin_whatsapp",
            tone="info",
            title="Você veio do WhatsApp",
            message="Seu pedido pode continuar por aqui, com carrinho e acompanhamento atualizados.",
            priority="contextual",
            actions=(
                Action(
                    ref="continue_checkout",
                    kind="link",
                    label="Continuar pedido",
                    href="/checkout",
                    priority="primary",
                ),
            ),
        ))

    return tuple(notices)


def _home_actions(last_order_ref: str | None) -> tuple[Action, ...]:
    if not last_order_ref:
        return ()
    return (
        Action(
            ref="reorder",
            kind="mutation",
            label="Repetir pedido",
            priority="primary",
            href=f"/api/v1/orders/{last_order_ref}/reorder/",
            method="POST",
            payload_schema={
                "type": "object",
                "properties": {
                    "mode": {"type": "string", "enum": ["replace", "append"]},
                    "idempotency_key": {"type": "string"},
                },
            },
            idempotency="required",
        ),
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


def _home_sections_copy(omotenashi: OmotenashiProjection) -> HomeSectionsCopyProjection:
    return HomeSectionsCopyProjection(
        availability_heading=_copy_entry("HOME_AVAILABILITY_HEADING", omotenashi=omotenashi),
        full_menu_cta=_copy_entry("HOME_FULL_MENU_CTA", omotenashi=omotenashi),
        how_it_works_heading=_copy_entry("HOME_HOW_IT_WORKS_HEADING", omotenashi=omotenashi),
        how_it_works_intro=_copy_entry("HOW_IT_WORKS_INTRO", omotenashi=omotenashi),
        how_online_heading=_copy_entry("HOME_HOW_ONLINE_HEADING", omotenashi=omotenashi),
        how_store_heading=_copy_entry("HOME_HOW_STORE_HEADING", omotenashi=omotenashi),
        how_step_choose=_copy_entry("HOME_HOW_STEP_CHOOSE", omotenashi=omotenashi),
        how_step_pay=_copy_entry("HOME_HOW_STEP_PAY", omotenashi=omotenashi),
        how_step_fulfill=_copy_entry("HOME_HOW_STEP_FULFILL", omotenashi=omotenashi),
        how_self_service_label=_copy_entry("HOME_HOW_SELF_SERVICE_LABEL", omotenashi=omotenashi),
        how_counter_label=_copy_entry("HOME_HOW_COUNTER_LABEL", omotenashi=omotenashi),
        how_hours_label=_copy_entry("HOME_HOW_HOURS_LABEL", omotenashi=omotenashi),
        how_hours_empty=_copy_entry("HOME_HOW_HOURS_EMPTY", omotenashi=omotenashi),
        how_online_choose_message=_copy_entry("HOW_ONLINE_CHOOSE_MESSAGE", omotenashi=omotenashi),
        how_online_pay_message=_copy_entry("HOW_ONLINE_PAY_MESSAGE", omotenashi=omotenashi),
        how_online_track_message=_copy_entry("HOW_ONLINE_TRACK_MESSAGE", omotenashi=omotenashi),
        how_store_self_service_message=_copy_entry("HOW_STORE_SELF_SERVICE_MESSAGE", omotenashi=omotenashi),
        how_store_counter_message=_copy_entry("HOW_STORE_COUNTER_MESSAGE", omotenashi=omotenashi),
        tomorrow_label=_copy_entry("HOME_TOMORROW_LABEL", omotenashi=omotenashi),
        tomorrow_hook=_copy_entry("TRACKING_TOMORROW_HOOK", omotenashi=omotenashi),
        whatsapp_cta=_copy_entry("HOME_WHATSAPP_CTA", omotenashi=omotenashi),
        whatsapp_cta_label=_copy_entry("HOME_WHATSAPP_CTA_LABEL", omotenashi=omotenashi),
    )


def _auth_copy(omotenashi: OmotenashiProjection) -> AuthCopyProjection:
    return AuthCopyProjection(
        phone_heading=_copy_entry("LOGIN_PHONE_HEADING", omotenashi=omotenashi),
        phone_subtitle=_copy_entry("LOGIN_PHONE_SUBTITLE", omotenashi=omotenashi),
        phone_cta_wa=_copy_entry("LOGIN_PHONE_CTA_WA", omotenashi=omotenashi),
        phone_cta_sms=_copy_entry("LOGIN_PHONE_CTA_SMS", omotenashi=omotenashi),
        trusted_device_message=_copy_entry("LOGIN_TRUSTED_DEVICE_MESSAGE", omotenashi=omotenashi),
        trusted_device_cta=_copy_entry("LOGIN_TRUSTED_DEVICE_CTA", omotenashi=omotenashi),
        trusted_other_phone=_copy_entry("LOGIN_TRUSTED_OTHER_PHONE", omotenashi=omotenashi),
        no_password_note=_copy_entry("LOGIN_NO_PASSWORD_NOTE", omotenashi=omotenashi),
        terms_note=_copy_entry("LOGIN_TERMS_NOTE", omotenashi=omotenashi),
        code_heading=_copy_entry("LOGIN_CODE_HEADING", omotenashi=omotenashi),
        code_help=_copy_entry("LOGIN_CODE_HELP", omotenashi=omotenashi),
        name_heading=_copy_entry("LOGIN_NAME_HEADING", omotenashi=omotenashi),
        name_subtitle=_copy_entry("LOGIN_NAME_SUBTITLE", omotenashi=omotenashi),
        name_cta=_copy_entry("LOGIN_NAME_CTA", omotenashi=omotenashi),
        auth_confirmed=_copy_entry("LOGIN_AUTH_CONFIRMED", omotenashi=omotenashi),
        device_trust_prompt=_copy_entry("DEVICE_TRUST_PROMPT", omotenashi=omotenashi),
        device_trust_cta=_copy_entry("DEVICE_TRUST_CTA", omotenashi=omotenashi),
        device_trust_skip_cta=_copy_entry("DEVICE_TRUST_SKIP_CTA", omotenashi=omotenashi),
        device_trust_redirecting=_copy_entry("DEVICE_TRUST_REDIRECTING", omotenashi=omotenashi),
        device_trust_saved=_copy_entry("DEVICE_TRUST_SAVED", omotenashi=omotenashi),
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
