"""Pricing rules — the operator-facing definition of each pricing modifier.

Each rule class declares a modifier's identity (``code``), its admin label and
``default_params``. Its ``RuleConfig`` row is the single source of truth for
that modifier's runtime behaviour: enabled state, params and channel scope.

Execution is rule-driven. The modifiers in ``shop.modifiers`` that read their
params through ``get_channel_rule_params`` (``AvailabilityDiscountModifier``,
``TimeWindowDiscountModifier``) skip entirely when their ``RuleConfig`` is
disabled or not scoped to the channel being priced — so disabling a rule in the
admin truly disables the discount.
"""

from __future__ import annotations

from datetime import time

from shopman.shop.rules import BaseRule


class D1Rule(BaseRule):
    """Desconto D-1 — sobras do dia anterior."""

    code = "shop.d1_discount"
    label = "Desconto de ontem"
    rule_type = "modifier"
    default_params = {"discount_percent": 50}

    def __init__(self, *, discount_percent: int = 50):
        self.discount_percent = discount_percent


class PromotionRule(BaseRule):
    """Promoções automáticas + cupons."""

    code = "shop.discount"
    label = "Promoções e Cupons"
    rule_type = "modifier"
    default_params = {}

    def __init__(self, **kwargs):
        pass


class EmployeeRule(BaseRule):
    """Desconto para funcionários (customer_group == staff)."""

    code = "shop.employee_discount"
    label = "Desconto Funcionário"
    rule_type = "modifier"
    default_params = {"discount_percent": 20, "group": "staff"}

    def __init__(self, *, discount_percent: int = 20, group: str = "staff"):
        self.discount_percent = discount_percent
        self.group = group


class HappyHourRule(BaseRule):
    """Desconto happy hour — horário configurável."""

    code = "shop.happy_hour"
    label = "Happy Hour"
    rule_type = "modifier"
    default_params = {"discount_percent": 25, "start": "17:30", "end": "18:00"}

    def __init__(
        self,
        *,
        discount_percent: int = 25,
        start: str = "17:30",
        end: str = "18:00",
    ):
        self.discount_percent = discount_percent
        self.start = time.fromisoformat(start)
        self.end = time.fromisoformat(end)
