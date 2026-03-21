"""
Shopman Pricing Modifiers — Modifiers para precificação.

Modifiers disponíveis:
- ItemPricingModifier: Aplica preços e calcula totais de linha
- SessionTotalModifier: Calcula total da sessão
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from .protocols import PricingBackend


class ItemPricingModifier:
    """
    Modifier que aplica preços e calcula totais de linha.

    Só atua se pricing_policy="internal".
    Se pricing_policy="external", preserva valores fornecidos pelo sistema externo.

    Ordem padrão: 10
    """

    code = "pricing.item"
    order = 10

    def __init__(self, backend: PricingBackend):
        self.backend = backend

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        if session.pricing_policy != "internal":
            return

        items = session.items
        trace = []
        modified = False

        for item in items:
            # 1. Aplica preço se não definido
            if item.get("unit_price_q") is None:
                sku = item["sku"]
                price = self.backend.get_price(sku, channel)
                if price is not None:
                    item["unit_price_q"] = price
                    modified = True
                    trace.append({
                        "line_id": item["line_id"],
                        "sku": sku,
                        "price_q": price,
                        "source": "internal",
                    })

            # 2. Calcula line_total_q
            from shopman.utils.monetary import monetary_mult

            qty = Decimal(str(item.get("qty", 0)))
            price = item.get("unit_price_q", 0)
            calculated_total = monetary_mult(qty, price)

            if item.get("line_total_q") != calculated_total:
                item["line_total_q"] = calculated_total
                modified = True

        if modified:
            session.items = items

        if trace:
            if not session.pricing_trace:
                session.pricing_trace = []
            session.pricing_trace.extend(trace)


class SessionTotalModifier:
    """
    Modifier que calcula total da sessão.

    Calcula pricing.total_q como soma de todos line_total_q.
    Funciona independente de pricing_policy.

    Ordem padrão: 50
    """

    code = "pricing.session_total"
    order = 50

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        total = sum(item.get("line_total_q", 0) for item in session.items)

        if not session.pricing:
            session.pricing = {}

        session.pricing["total_q"] = total
        session.pricing["items_count"] = len(session.items)
