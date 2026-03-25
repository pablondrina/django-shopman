"""
Shop — Custom order modifiers.

Modifiers follow the Ordering Modifier protocol:
- code: str — unique identifier
- order: int — execution order (lower = first)
- apply(*, channel, session, ctx) -> None — mutates session in-place

Execution order:
  10  pricing.item          — base price from backend (qty-aware)
  15  shop.d1_discount      — D-1 markdown
  20  shop.promotion        — auto-promotions
  25  shop.coupon           — coupon discount
  50  pricing.session_total — recalculate total
  60  shop.employee_discount
  65  shop.happy_hour
"""
from __future__ import annotations

import logging
from datetime import time
from typing import Any

from django.utils import timezone
from shopman.utils.monetary import monetary_div

logger = logging.getLogger(__name__)

# ── Configurable defaults ──────────────────────────────────────────
D1_DISCOUNT_PERCENT = 50
EMPLOYEE_DISCOUNT_PERCENT = 20
HAPPY_HOUR_DISCOUNT_PERCENT = 10
HAPPY_HOUR_START = time(16, 0)
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
        config = getattr(channel, "config", None) or {}
        rules = config.get("rules", {})
        percent = rules.get("d1_discount_percent", self.discount_percent)

        availability = (session.data or {}).get("availability", {})

        items = session.items or []
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


class PromotionModifier:
    """
    Aplica promoções ativas automaticamente.

    Busca promoções válidas (is_active, dentro do período) e aplica a
    de maior desconto para cada item que atenda os critérios (SKU ou coleção).
    """

    code = "shop.promotion"
    order = 20

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shop.models import Promotion

        now = timezone.now()
        promotions = list(
            Promotion.objects.filter(
                is_active=True,
                valid_from__lte=now,
                valid_until__gte=now,
            )
        )
        if not promotions:
            return

        items = session.items or []
        session_total = sum(item.get("line_total_q", 0) for item in items)
        modified = False

        for item in items:
            sku = item.get("sku", "")
            price_q = item.get("unit_price_q", 0)
            if not price_q:
                continue

            # Skip items already discounted by D-1
            applied = item.get("modifiers_applied", [])
            if any(m.get("type") == "d1_discount" for m in applied):
                continue

            best_discount_q = 0
            best_promo = None

            for promo in promotions:
                if promo.min_order_q and session_total < promo.min_order_q:
                    continue
                if not self._matches(promo, sku, ctx):
                    continue

                discount_q = self._calc_discount(promo, price_q)
                if discount_q > best_discount_q:
                    best_discount_q = discount_q
                    best_promo = promo

            if best_promo and best_discount_q > 0:
                item["unit_price_q"] = price_q - best_discount_q
                item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))
                item.setdefault("modifiers_applied", []).append({
                    "type": "promotion",
                    "promotion_id": best_promo.pk,
                    "promotion_name": best_promo.name,
                    "discount_q": best_discount_q,
                })
                modified = True

        if modified:
            session.update_items(items)

    @staticmethod
    def _matches(promo: Any, sku: str, ctx: dict) -> bool:
        if promo.skus and sku not in promo.skus:
            return False
        if promo.collections:
            item_collections = ctx.get("sku_collections", {}).get(sku, [])
            if not any(c in promo.collections for c in item_collections):
                return False
        return True

    @staticmethod
    def _calc_discount(promo: Any, price_q: int) -> int:
        if promo.type == "percent":
            return monetary_div(price_q * promo.value, 100)
        return min(promo.value, price_q)


class CouponModifier:
    """
    Aplica desconto de cupom.

    Lê session.data["coupon_code"], busca Coupon + Promotion vinculada,
    e aplica o desconto nos itens elegíveis.
    """

    code = "shop.coupon"
    order = 25

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        coupon_code = (session.data or {}).get("coupon_code")
        if not coupon_code:
            return

        from shop.models import Coupon

        try:
            coupon = Coupon.objects.select_related("promotion").get(
                code=coupon_code,
                is_active=True,
            )
        except Coupon.DoesNotExist:
            return

        if not coupon.is_available:
            return

        promo = coupon.promotion
        now = timezone.now()
        if not promo.is_active or now < promo.valid_from or now > promo.valid_until:
            return

        items = session.items or []
        session_total = sum(item.get("line_total_q", 0) for item in items)
        if promo.min_order_q and session_total < promo.min_order_q:
            return

        total_discount_q = 0
        modified = False

        for item in items:
            sku = item.get("sku", "")
            price_q = item.get("unit_price_q", 0)
            if not price_q:
                continue

            # Skip items already discounted by D-1
            applied = item.get("modifiers_applied", [])
            if any(m.get("type") == "d1_discount" for m in applied):
                continue

            if not PromotionModifier._matches(promo, sku, ctx):
                continue

            discount_q = PromotionModifier._calc_discount(promo, price_q)
            if discount_q > 0:
                item["unit_price_q"] = price_q - discount_q
                item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))
                item.setdefault("modifiers_applied", []).append({
                    "type": "coupon",
                    "coupon_code": coupon_code,
                    "discount_q": discount_q,
                })
                total_discount_q += discount_q * int(item.get("qty", 1))
                modified = True

        if modified:
            session.update_items(items)

        if not session.pricing:
            session.pricing = {}
        session.pricing["coupon"] = {
            "code": coupon_code,
            "discount_q": total_discount_q,
        }


class EmployeeDiscountModifier:
    """
    20% discount for employees (customer_group == "staff").

    Applied per-item. Adjusts unit_price_q and line_total_q on session.items.
    """

    code = "shop.employee_discount"
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

    code = "shop.happy_hour"
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
