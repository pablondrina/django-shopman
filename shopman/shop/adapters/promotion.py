"""
Promotion adapter — encapsula acesso a Promotion, Coupon e DeliveryZone.

Separa shop/ de storefront/ nos modifiers. Adapters podem importar de
qualquer app; modifiers e services de shop/ não devem.
"""
from __future__ import annotations

from typing import Any


def get_active_promotions(now) -> list[Any]:
    """Promoções automáticas ativas (excluindo cupom-only)."""
    from shopman.storefront.models import Promotion

    return list(
        Promotion.objects.filter(
            is_active=True,
            valid_from__lte=now,
            valid_until__gte=now,
        ).exclude(
            coupons__isnull=False,
        )
    )


def get_coupon_promotion(code: str, now) -> Any | None:
    """Retorna a promoção atrelada ao cupom se válida, ou None."""
    from shopman.storefront.models import Coupon

    try:
        coupon = Coupon.objects.select_related("promotion").get(code=code, is_active=True)
    except Coupon.DoesNotExist:
        return None

    if not coupon.is_available:
        return None

    promo = coupon.promotion
    if promo.is_active and promo.valid_from <= now <= promo.valid_until:
        return promo
    return None


def match_delivery_zone(postal_code: str, neighborhood: str) -> Any | None:
    """Retorna a DeliveryZone ativa de maior prioridade, ou None."""
    from shopman.storefront.models import DeliveryZone

    return DeliveryZone.match(postal_code=postal_code, neighborhood=neighborhood)
