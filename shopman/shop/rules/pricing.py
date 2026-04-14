"""Pricing rules — wrappers around existing modifiers for admin visibility.

Each rule class wraps an existing modifier from shop.modifiers. For R5, these
rules exist so the operator can view/edit/disable them via admin. The actual
execution continues via the modifiers registered in channels.setup.

When the operator disables a rule in admin, the engine filters it out —
but the underlying modifier still runs (channels.setup registers it
unconditionally). Full migration to rule-driven execution happens in R8.
"""

from __future__ import annotations

from datetime import time


class D1Rule:
    """Desconto D-1 — sobras do dia anterior."""

    code = "shop.d1_discount"
    label = "Desconto D-1 (sobras)"
    rule_type = "modifier"
    default_params = {"discount_percent": 50}

    def __init__(self, *, discount_percent: int = 50):
        self.discount_percent = discount_percent


class PromotionRule:
    """Promoções automáticas + cupons."""

    code = "shop.discount"
    label = "Promoções e Cupons"
    rule_type = "modifier"
    default_params = {}

    def __init__(self, **kwargs):
        pass


class EmployeeRule:
    """Desconto para funcionários (customer_group == staff)."""

    code = "shop.employee_discount"
    label = "Desconto Funcionário"
    rule_type = "modifier"
    default_params = {"discount_percent": 20, "group": "staff"}

    def __init__(self, *, discount_percent: int = 20, group: str = "staff"):
        self.discount_percent = discount_percent
        self.group = group


class HappyHourRule:
    """Desconto happy hour — horário configurável."""

    code = "shop.happy_hour"
    label = "Happy Hour"
    rule_type = "modifier"
    default_params = {"discount_percent": 10, "start": "16:00", "end": "18:00"}

    def __init__(
        self,
        *,
        discount_percent: int = 10,
        start: str = "16:00",
        end: str = "18:00",
    ):
        self.discount_percent = discount_percent
        self.start = time.fromisoformat(start)
        self.end = time.fromisoformat(end)
