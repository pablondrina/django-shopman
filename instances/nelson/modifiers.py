"""
Nelson Boulangerie — modifiers específicos da instância.

D-1 Discount: desconto em itens do dia anterior (perecíveis).
Happy Hour: desconto por horário ("Hora da Xepa").

Para ativar, adicione ao SHOPMAN_INSTANCE_MODIFIERS em settings:
    SHOPMAN_INSTANCE_MODIFIERS = [
        "nelson.modifiers.D1DiscountModifier",
        "nelson.modifiers.HappyHourModifier",
    ]
"""

from __future__ import annotations

import logging
from datetime import time
from typing import Any

from django.conf import settings
from django.utils import timezone
from shopman.utils.monetary import monetary_div

logger = logging.getLogger(__name__)

# ── Configurable defaults ──────────────────────────────────────────
D1_DISCOUNT_PERCENT = 50
HAPPY_HOUR_DISCOUNT_PERCENT = 25
HAPPY_HOUR_START = time(17, 30)
HAPPY_HOUR_END = time(18, 0)


class D1DiscountModifier:
    """
    Desconto D-1 — aplica desconto em itens com estoque apenas D-1
    (sobras do dia anterior).

    Configurável via channel config: rules.d1_discount_percent (default 50).
    Requer que o item tenha {"is_d1": true} em session.data["availability"]
    ou em item["is_d1"].
    """

    code = "shop.d1_discount"
    order = 15

    def __init__(self, *, discount_percent: int = D1_DISCOUNT_PERCENT):
        self.discount_percent = discount_percent

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        availability = (session.data or {}).get("availability", {})
        items = session.items or []
        if not any(
            item.get("is_d1", False)
            or availability.get(item.get("sku", ""), {}).get("is_d1", False)
            for item in items
        ):
            return

        config = getattr(channel, "config", None) or {}
        channel_rules = config.get("rules", {})
        if "d1_discount_percent" in channel_rules:
            percent = channel_rules["d1_discount_percent"]
        else:
            from shopman.shop.rules.engine import get_rule_params
            percent = get_rule_params("d1_discount").get("discount_percent", self.discount_percent)

        modified = False
        for item in items:
            sku = item.get("sku", "")
            is_d1 = item.get("is_d1", False) or availability.get(sku, {}).get("is_d1", False)
            if not is_d1:
                continue

            original_q = item.get("unit_price_q", 0)
            if not original_q:
                continue

            discount_q = monetary_div(original_q * percent, 100)
            item["unit_price_q"] = original_q - discount_q
            item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))
            item.setdefault("modifiers_applied", []).append(
                {"type": "d1_discount", "discount_percent": percent, "original_price_q": original_q}
            )
            modified = True

        if modified:
            session.update_items(items)
            total_discount_q = sum(
                (m["original_price_q"] - item.get("unit_price_q", 0)) * int(item.get("qty", 1))
                for item in items
                for m in item.get("modifiers_applied", [])
                if m.get("type") == "d1_discount"
            )
            pricing = session.pricing or {}
            if total_discount_q > 0:
                pricing["d1_discount"] = {"total_discount_q": total_discount_q, "label": "D-1"}
            else:
                pricing.pop("d1_discount", None)
            session.pricing = pricing
            session.save(update_fields=["pricing"])


class HappyHourModifier:
    """
    Desconto por horário (Happy Hour / "Hora da Xepa").

    Params lidos de RuleConfig "happy_hour" (discount_percent, start, end).
    Fallback: args do construtor → SHOPMAN_HAPPY_HOUR_* settings → constantes do módulo.

    Não se aplica a itens com employee_discount.
    Não se aplica ao canal web (evita divergência vitrine vs carrinho).
    """

    code = "shop.happy_hour"
    order = 65

    def __init__(
        self,
        *,
        discount_percent: int = HAPPY_HOUR_DISCOUNT_PERCENT,
        start: time | None = None,
        end: time | None = None,
    ):
        self._discount_percent = discount_percent
        self._start = start
        self._end = end

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        if (session.data or {}).get("origin_channel") == "web":
            return

        # Resolve params: RuleConfig > constructor arg > settings > module constant
        from shopman.shop.rules.engine import get_rule_params
        rc = get_rule_params("happy_hour")

        discount_percent = rc.get("discount_percent", self._discount_percent)

        if "start" in rc:
            h, m = map(int, rc["start"].split(":"))
            start = time(h, m)
        elif self._start is not None:
            start = self._start
        else:
            raw = getattr(settings, "SHOPMAN_HAPPY_HOUR_START", "17:30")
            h, m = map(int, raw.split(":"))
            start = time(h, m)

        if "end" in rc:
            h, m = map(int, rc["end"].split(":"))
            end = time(h, m)
        elif self._end is not None:
            end = self._end
        else:
            raw = getattr(settings, "SHOPMAN_HAPPY_HOUR_END", "18:00")
            h, m = map(int, raw.split(":"))
            end = time(h, m)

        now = timezone.localtime().time()
        if not (start <= now < end):
            return

        items = session.items or []
        modified = False
        for item in items:
            applied = item.get("modifiers_applied", [])
            if any(m.get("type") == "employee_discount" for m in applied):
                continue

            original_q = item.get("unit_price_q", 0)
            discount_q = monetary_div(original_q * discount_percent, 100)
            item["unit_price_q"] = original_q - discount_q
            item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))
            item.setdefault("modifiers_applied", []).append(
                {"type": "happy_hour", "discount_percent": discount_percent}
            )
            modified = True

        if modified:
            session.update_items(items)
            total_discount_q = sum(
                monetary_div(item.get("unit_price_q", 0) * discount_percent, 100 - discount_percent)
                * int(item.get("qty", 1))
                for item in items
                if any(m.get("type") == "happy_hour" for m in item.get("modifiers_applied", []))
            )
            pricing = session.pricing or {}
            if total_discount_q > 0:
                pricing["happy_hour"] = {"total_discount_q": total_discount_q, "label": "Happy Hour"}
            else:
                pricing.pop("happy_hour", None)
            session.pricing = pricing
            session.save(update_fields=["pricing"])
