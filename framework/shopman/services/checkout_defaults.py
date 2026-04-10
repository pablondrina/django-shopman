"""
Checkout defaults — lê e grava defaults de checkout por cliente por canal.

Usa CustomerPreference com category="checkout" e key "{channel_ref}:{field}".
Preferences explícitas (salvas pelo cliente) nunca são sobrescritas por inferidas.
"""

from __future__ import annotations

import logging
from collections import Counter
from decimal import Decimal

from shopman.adapters import get_adapter

logger = logging.getLogger(__name__)

CATEGORY = "checkout"

KEYS = (
    "fulfillment_type",
    "delivery_address_id",
    "delivery_timing",
    "delivery_time_slot",
    "payment_method",
    "order_notes",
)

# Keys that can be inferred from order history (order_notes is explicit-only)
INFERABLE_KEYS = (
    "fulfillment_type",
    "delivery_address_id",
    "delivery_timing",
    "delivery_time_slot",
    "payment_method",
)

# Minimum orders in channel before inference kicks in
MIN_ORDERS_FOR_INFERENCE = 3

# Minimum frequency ratio to infer a default (70%)
MIN_CONFIDENCE = Decimal("0.70")


class CheckoutDefaultsService:
    """Lê e grava checkout defaults usando CustomerPreference."""

    @classmethod
    def get_defaults(cls, customer_ref: str, channel_ref: str) -> dict:
        """Retorna dict com defaults do cliente para o canal.

        Returns:
            {"fulfillment_type": "delivery", "payment_method": "pix", ...}
            Apenas keys com valor são incluídas.
        """
        adapter = get_adapter("customer")
        prefs = adapter.get_preferences(customer_ref, category=CATEGORY)
        prefix = f"{channel_ref}:"
        return {
            p["key"].removeprefix(prefix): p["value"]
            for p in prefs
            if p["key"].startswith(prefix)
        }

    @classmethod
    def save_defaults(
        cls,
        customer_ref: str,
        channel_ref: str,
        data: dict,
        source: str = "checkout",
    ) -> None:
        """Salva defaults explícitos (usuário marcou 'salvar como padrão')."""
        adapter = get_adapter("customer")
        for key, value in data.items():
            if key in KEYS and value:
                adapter.set_preference(
                    customer_ref=customer_ref,
                    category=CATEGORY,
                    key=f"{channel_ref}:{key}",
                    value=value,
                    preference_type="explicit",
                    confidence=1.0,
                    source=source,
                )

    @classmethod
    def infer_from_history(
        cls,
        customer_ref: str,
        channel_ref: str,
        orders: list,
    ) -> dict:
        """Infere defaults a partir do histórico de pedidos no canal.

        Args:
            customer_ref: Customer ref
            channel_ref: Channel ref
            orders: List of Order objects (mesma canal, mais recentes primeiro)

        Returns:
            Dict of inferred keys and values that were saved.
        """
        if len(orders) < MIN_ORDERS_FOR_INFERENCE:
            return {}

        # Collect signals from orders
        signals: dict[str, list] = {k: [] for k in INFERABLE_KEYS}
        for order in orders:
            data = order.data or {}
            if ft := data.get("fulfillment_type"):
                signals["fulfillment_type"].append(ft)
            if addr_id := data.get("delivery_address_id"):
                signals["delivery_address_id"].append(addr_id)
            if dd := data.get("delivery_date"):
                signals["delivery_timing"].append(_classify_timing(dd, order))
            if ts := data.get("delivery_time_slot"):
                signals["delivery_time_slot"].append(ts)
            payment = data.get("payment", {})
            if pm := (payment.get("method") if isinstance(payment, dict) else None):
                signals["payment_method"].append(pm)

        # Check existing explicit preferences (never overwrite)
        adapter = get_adapter("customer")
        existing_prefs = adapter.get_preferences(customer_ref, category=CATEGORY)
        prefix = f"{channel_ref}:"
        existing_explicit = {
            p["key"].removeprefix(prefix)
            for p in existing_prefs
            if p["key"].startswith(prefix) and p.get("preference_type") == "explicit"
        }

        # Infer most frequent value for each key
        inferred = {}
        total = len(orders)
        for key in INFERABLE_KEYS:
            if key in existing_explicit:
                continue
            values = signals[key]
            if not values:
                continue
            counter = Counter(values)
            most_common_value, count = counter.most_common(1)[0]
            confidence = Decimal(str(round(count / total, 2)))
            if confidence >= MIN_CONFIDENCE:
                adapter.set_preference(
                    customer_ref=customer_ref,
                    category=CATEGORY,
                    key=f"{channel_ref}:{key}",
                    value=most_common_value,
                    preference_type="inferred",
                    confidence=float(confidence),
                    source=f"inferred:{total}_orders",
                )
                inferred[key] = most_common_value

        return inferred


def _classify_timing(delivery_date: str, order) -> str:
    """Classify a delivery_date relative to order creation as timing category."""
    try:
        from datetime import date as date_type

        order_date = order.created_at.date()
        chosen = date_type.fromisoformat(delivery_date)
        delta = (chosen - order_date).days
        if delta <= 0:
            return "same_day"
        elif delta == 1:
            return "next_day"
        else:
            return "future"
    except Exception:
        return "same_day"
