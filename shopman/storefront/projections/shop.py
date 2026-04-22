"""ShopProjection — typed read model for the Shop singleton in storefront templates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shopman.shop.models import Shop


@dataclass(frozen=True)
class SocialLinkProjection:
    url: str
    platform: str
    label: str
    icon_svg: str


@dataclass(frozen=True)
class ShopProjection:
    brand_name: str
    tagline: str
    description: str
    description_html: str
    logo_name: str
    logo_url: str
    color_mode: str
    theme_color: str
    background_color: str
    design_tokens: dict
    whatsapp_url: str
    phone: str
    phone_display: str
    phone_url: str
    email: str
    full_address: str
    maps_url: str
    default_city: str
    social_links: tuple[SocialLinkProjection, ...]


def build_shop_projection(shop: "Shop") -> ShopProjection:
    logo_name = shop.logo.name if shop.logo else ""
    logo_url = shop.logo.url if shop.logo else ""

    resolved = shop.social_links_resolved
    social_links = tuple(
        SocialLinkProjection(
            url=link["url"],
            platform=link["platform"],
            label=link["label"],
            icon_svg=link["icon_svg"],
        )
        for link in resolved
    )

    return ShopProjection(
        brand_name=shop.brand_name or shop.name,
        tagline=shop.tagline,
        description=shop.description,
        description_html=shop.description_html,
        logo_name=logo_name,
        logo_url=logo_url,
        color_mode=shop.color_mode,
        theme_color=shop.theme_color,
        background_color=shop.background_color,
        design_tokens=shop.design_tokens,
        whatsapp_url=shop.whatsapp_url,
        phone=shop.phone,
        phone_display=shop.phone_display,
        phone_url=shop.phone_url,
        email=shop.email,
        full_address=shop.full_address,
        maps_url=shop.maps_url,
        default_city=shop.default_city,
        social_links=social_links,
    )
