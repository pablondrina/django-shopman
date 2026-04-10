"""
Pricing modifiers — precificação de itens e totais.

Inline de shopman.pricing.modifiers.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from shopman.offerman.models import ListingItem, Product

logger = logging.getLogger(__name__)


class OffermanPricingBackend:
    """Resolve preço pela cascata: grupo do cliente → listing do canal → preço base."""

    def get_price(self, sku: str, channel: Any, customer=None, qty: int = 1) -> int | None:
        # 1. Preço do grupo do cliente (se identificado e tem grupo com listing)
        if customer and hasattr(customer, "group") and customer.group:
            listing_ref = getattr(customer.group, "listing_ref", None)
            if listing_ref:
                item = self._get_listing_item(listing_ref, sku, qty=qty)
                if item and item.is_available:
                    return item.price_q

        # 2. Preço do canal (via listing do canal)
        channel_listing = getattr(channel, "listing_ref", None) if channel else None
        if channel_listing:
            item = self._get_listing_item(channel_listing, sku, qty=qty)
            if item and item.is_available:
                return item.price_q

        # 3. Preço base do produto
        try:
            product = Product.objects.get(sku=sku)
            return product.base_price_q
        except Product.DoesNotExist:
            return None

    def _get_listing_item(self, listing_ref, sku, qty=1):
        """Find the ListingItem with the highest min_qty tier <= qty."""
        return (
            ListingItem.objects.filter(
                listing__ref=listing_ref,
                product__sku=sku,
                min_qty__lte=qty,
                is_published=True,
            )
            .order_by("-min_qty")
            .first()
        )


class ItemPricingModifier:
    """
    Modifier que aplica preços e calcula totais de linha. Ordem: 10.

    Para internal pricing: sempre re-resolve o preço do backend a cada run,
    garantindo que discount modifiers partam do preço base correto.
    Limpa modifiers_applied para que discounts sejam recalculados do zero.
    """

    code = "pricing.item"
    order = 10

    def __init__(self, backend):
        self.backend = backend

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        items = session.items
        trace = []
        modified = False

        customer = ctx.get("customer")
        for item in items:
            sku = item["sku"]

            # Always clear discount state — modifiers recalculate each run
            if item.pop("modifiers_applied", None):
                modified = True

            if session.pricing_policy == "internal":
                # Always re-resolve price from backend
                qty_val = int(item.get("qty", 1))
                kwargs = {"qty": qty_val}
                if customer is not None:
                    kwargs["customer"] = customer
                price = self.backend.get_price(sku, channel, **kwargs)
                if price is not None:
                    if item.get("unit_price_q") != price:
                        item["unit_price_q"] = price
                        modified = True
                        trace.append({
                            "line_id": item["line_id"],
                            "sku": sku,
                            "price_q": price,
                            "source": "internal",
                        })
            else:
                # External: restore base price if it was modified by discounts
                base = item.get("_base_price_q")
                if base is not None:
                    if item.get("unit_price_q") != base:
                        item["unit_price_q"] = base
                        modified = True
                else:
                    # First run — save current price as base
                    item["_base_price_q"] = item.get("unit_price_q", 0)

            from shopman.utils.monetary import monetary_mult

            qty = Decimal(str(item.get("qty", 0)))
            unit_price = item.get("unit_price_q", 0)
            calculated_total = monetary_mult(qty, unit_price)

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
