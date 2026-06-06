"""
Nelson Boulangerie — modifiers específicos da instância.

Happy Hour: desconto por horário ("Hora da Xepa").

Para ativar, adicione ao SHOPMAN_INSTANCE_MODIFIERS em settings:
    SHOPMAN_INSTANCE_MODIFIERS = [
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
HAPPY_HOUR_DISCOUNT_PERCENT = 25
HAPPY_HOUR_START = time(17, 30)
HAPPY_HOUR_END = time(18, 0)


def _is_non_merchandise_line(item: dict) -> bool:
    meta = item.get("meta") or {}
    return item.get("sku") == "__DELIVERY_FEE__" or meta.get("type") in {"delivery_fee"}


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
            if _is_non_merchandise_line(item):
                continue
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
