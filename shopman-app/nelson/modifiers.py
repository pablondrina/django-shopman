"""
Nelson Boulangerie — Custom order modifiers.

Modifiers follow the Ordering Modifier protocol:
- code: str — unique identifier
- order: int — execution order (lower = first)
- apply(*, channel, session, ctx) -> None — mutates session in-place
"""
from __future__ import annotations

from datetime import time
from typing import Any

from django.utils import timezone

from shopman.utils.monetary import monetary_div


# ── Configurable defaults ──────────────────────────────────────────
EMPLOYEE_DISCOUNT_PERCENT = 20
HAPPY_HOUR_DISCOUNT_PERCENT = 10
HAPPY_HOUR_START = time(16, 0)
HAPPY_HOUR_END = time(18, 0)


class EmployeeDiscountModifier:
    """
    20% discount for employees (customer_group == "staff").

    Applied per-item. Adjusts unit_price_q and line_total_q on session.items.
    """

    code = "nelson.employee_discount"
    order = 60  # After canonical pricing (10, 50), before session total recalc

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        customer_group = (session.data or {}).get("customer", {}).get("group", "")
        if customer_group != "staff":
            return

        items = session.items or []
        for item in items:
            original_q = item.get("unit_price_q", 0)
            discount_q = monetary_div(original_q * EMPLOYEE_DISCOUNT_PERCENT, 100)
            item["unit_price_q"] = original_q - discount_q
            item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))
            item.setdefault("modifiers_applied", []).append(
                {"type": "employee_discount", "discount_percent": EMPLOYEE_DISCOUNT_PERCENT}
            )


class HappyHourModifier:
    """
    10% discount during happy hour (16h-18h by default).

    Applied per-item. Does NOT stack with employee discount.
    """

    code = "nelson.happy_hour"
    order = 65  # After employee discount

    def __init__(
        self,
        *,
        discount_percent: int = HAPPY_HOUR_DISCOUNT_PERCENT,
        start: time = HAPPY_HOUR_START,
        end: time = HAPPY_HOUR_END,
    ):
        self.discount_percent = discount_percent
        self.start = start
        self.end = end

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        now = timezone.localtime().time()
        if not (self.start <= now < self.end):
            return

        items = session.items or []
        for item in items:
            # Skip if employee discount already applied
            applied = item.get("modifiers_applied", [])
            if any(m.get("type") == "employee_discount" for m in applied):
                continue

            original_q = item.get("unit_price_q", 0)
            discount_q = monetary_div(original_q * self.discount_percent, 100)
            item["unit_price_q"] = original_q - discount_q
            item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))
            item.setdefault("modifiers_applied", []).append(
                {"type": "happy_hour", "discount_percent": self.discount_percent}
            )
