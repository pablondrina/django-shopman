"""FOMO no storefront — junta o contexto de domínio com a derivação de badges.

Camada fina de propósito: os fatos vêm de ``shop.services.fomo`` (que fala com
Stockman/Craftsman) e a decisão de exibição vem de ``presentation.fomo`` (que é
pura). Aqui só acontece a composição.
"""

from __future__ import annotations

from shopman.shop.services import fomo as fomo_context
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation.fomo import badges_for_product


def badges_for_sku(sku: str, *, channel_ref: str | None = None) -> tuple:
    """Badges FOMO atuais de um SKU. Tupla vazia quando não há urgência real."""
    channel_ref = channel_ref or STOREFRONT_CHANNEL_REF
    context = fomo_context.context_for_sku(sku, channel_ref=channel_ref)
    return badges_for_product(sku, **context)
