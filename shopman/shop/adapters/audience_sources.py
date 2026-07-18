"""Audience adapter — encapsula o acesso às fontes de audiência do storefront.

Mesmo papel do ``adapters/promotion.py``: os favoritos e as assinaturas de
alerta são models do storefront, e ``shop/services/`` não importa superfície
direto (ADR-001). O adapter é a única porta.

Devolve dados crus (refs, telefones) — quem decide quem recebe é o
``services/audience.py``.
"""

from __future__ import annotations


def favorite_customer_refs(sku: str) -> list[str]:
    """Refs de clientes que favoritaram este SKU."""
    from shopman.storefront.models import CustomerFavorite

    return list(
        CustomerFavorite.objects.filter(sku=sku)
        .values_list("customer_ref", flat=True)
        .distinct()
    )


def pending_alert_contacts(sku: str) -> list[tuple[str, str]]:
    """``(telefone, customer_ref)`` de cada assinatura pendente deste SKU.

    Inclui os dois gatilhos (``stock_back`` e ``production_ready``): quem pediu
    para ser avisado sobre o produto quer saber, seja qual for o motivo.
    """
    from shopman.storefront.models import StockAlertSubscription

    return list(
        StockAlertSubscription.objects.filter(
            sku=sku, notified_at__isnull=True
        ).values_list("contact_phone", "customer_ref")
    )
