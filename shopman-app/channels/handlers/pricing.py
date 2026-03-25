"""
Pricing modifiers — precificação de itens e totais.

Inline de shopman.pricing.modifiers.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from channels.protocols import PricingBackend


class ItemPricingModifier:
    """Modifier que aplica preços e calcula totais de linha. Ordem: 10"""

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
            if item.get("unit_price_q") is None:
                sku = item["sku"]
                qty_val = int(item.get("qty", 1))
                price = self.backend.get_price(sku, channel, qty=qty_val)
                if price is not None:
                    item["unit_price_q"] = price
                    modified = True
                    trace.append({"line_id": item["line_id"], "sku": sku, "price_q": price, "source": "internal"})

            from shopman.utils.monetary import monetary_mult

            qty = Decimal(str(item.get("qty", 0)))
            price = item.get("unit_price_q", 0)
            calculated_total = monetary_mult(qty, price)

            if item.get("line_total_q") != calculated_total:
                item["line_total_q"] = calculated_total
                modified = True

        if modified:
            session.update_items(items)

        if trace:
            if not session.pricing_trace:
                session.pricing_trace = []
            session.pricing_trace.extend(trace)


class SessionTotalModifier:
    """Modifier que calcula total da sessão. Ordem: 50"""

    code = "pricing.session_total"
    order = 50

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        total = sum(item.get("line_total_q", 0) for item in session.items)

        if not session.pricing:
            session.pricing = {}

        session.pricing["total_q"] = total
        session.pricing["items_count"] = len(session.items)


__all__ = ["ItemPricingModifier", "SessionTotalModifier"]
