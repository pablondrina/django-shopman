"""
Shop — Custom order modifiers.

Modifiers follow the Ordering Modifier protocol:
- code: str — unique identifier
- order: int — execution order (lower = first)
- apply(*, channel, session, ctx) -> None — mutates session in-place

Execution order:
  10  pricing.item          — base price from backend (qty-aware)
  15  shop.d1_discount      — D-1 markdown (priority, skips other discounts)
  20  shop.discount         — promotions + coupons (maior desconto ganha)
  50  pricing.session_total — recalculate total
  60  shop.employee_discount
  65  shop.happy_hour
  70  shop.delivery_fee     — taxa de entrega por zona (só delivery)

Discount policy — "maior desconto ganha":
  Per item, only ONE discount applies (the best one).
  D-1 has absolute priority and prevents all other discounts.
  Employee and HappyHour are post-pricing and mutually exclusive.
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


class DiscountModifier:
    """
    Desconto unificado — promoções automáticas + cupom.

    Política: "maior desconto ganha" por item.
    Para cada item elegível, coleta candidatos (promoções ativas + cupom),
    calcula o desconto de cada sobre o preço BASE, e aplica apenas o maior.

    Não se aplica a itens com D-1 (prioridade absoluta).

    Promoções com ``fulfillment_types`` e sessão **sem** ``fulfillment_type`` ainda assim
    são avaliadas como na vitrine (qualquer tipo permitido que case) — evita cardápio com
    "Delivery -R$2" e carrinho só com percentual.
    """

    code = "shop.discount"
    order = 20

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shopman.models import Coupon, Promotion

        # Inject fulfillment_type from session data into ctx for matching
        fulfillment_type = (session.data or {}).get("fulfillment_type", "")
        if fulfillment_type:
            ctx.setdefault("fulfillment_type", fulfillment_type)

        now = timezone.now()

        # Collect active AUTO-promotions (exclude coupon-only promotions)
        promotions = list(
            Promotion.objects.filter(
                is_active=True,
                valid_from__lte=now,
                valid_until__gte=now,
            ).exclude(
                coupons__isnull=False,
            )
        )

        # Collect coupon (if applied)
        coupon_code = (session.data or {}).get("coupon_code")
        coupon_promo = None
        if coupon_code:
            try:
                coupon = Coupon.objects.select_related("promotion").get(
                    code=coupon_code, is_active=True,
                )
                if coupon.is_available:
                    promo = coupon.promotion
                    if promo.is_active and promo.valid_from <= now <= promo.valid_until:
                        coupon_promo = promo
            except Coupon.DoesNotExist:
                pass

        if not promotions and not coupon_promo:
            if not session.pricing:
                session.pricing = {}
            session.pricing.pop("coupon", None)
            session.pricing.pop("discount", None)
            return

        items = session.items or []
        # Coleções por SKU — necessário para promoções por coleção (mesma regra no vitrine)
        if items and not ctx.get("sku_collections"):
            try:
                from shopman.offering.models import CollectionItem

                line_skus = [i.get("sku") for i in items if i.get("sku")]
                col_map: dict[str, list[str]] = {}
                for ci in CollectionItem.objects.filter(product__sku__in=line_skus).select_related(
                    "collection",
                ):
                    col_map.setdefault(ci.product.sku, []).append(ci.collection.slug)
                ctx["sku_collections"] = col_map
            except Exception:
                pass

        session_total = sum(item.get("line_total_q", 0) for item in items)
        modified = False
        total_coupon_discount_q = 0
        discounts_applied = []  # Persisted in session.pricing

        for item in items:
            sku = item.get("sku", "")
            price_q = item.get("unit_price_q", 0)
            if not price_q:
                continue

            # D-1 items skip all other discounts
            applied = item.get("modifiers_applied", [])
            if any(m.get("type") == "d1_discount" for m in applied):
                continue

            # Find best discount candidate
            best_discount_q = 0
            best_source = None  # (type, name)

            # Evaluate auto-promotions
            for promo in promotions:
                if promo.min_order_q and session_total < promo.min_order_q:
                    continue
                if not self._matches(promo, sku, ctx):
                    continue
                discount_q = self._calc_discount(promo, price_q)
                if discount_q > best_discount_q:
                    best_discount_q = discount_q
                    best_source = ("promotion", promo.name, promo.pk)

            # Evaluate coupon
            if coupon_promo:
                if not (coupon_promo.min_order_q and session_total < coupon_promo.min_order_q):
                    if self._matches(coupon_promo, sku, ctx):
                        coupon_discount_q = self._calc_discount(coupon_promo, price_q)
                        if coupon_discount_q >= best_discount_q:
                            best_discount_q = coupon_discount_q
                            best_source = ("coupon", coupon_code, None)

            # Apply winner
            if best_source and best_discount_q > 0:
                item["unit_price_q"] = price_q - best_discount_q
                item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))

                source_type, source_name, source_id = best_source
                modifier_info = {
                    "type": source_type,
                    "name": source_name,
                    "original_price_q": price_q,
                    "discount_q": best_discount_q,
                }
                if source_id:
                    modifier_info["promotion_id"] = source_id
                item.setdefault("modifiers_applied", []).append(modifier_info)
                modified = True

                qty = int(item.get("qty", 1))
                discounts_applied.append({
                    "sku": sku,
                    "type": source_type,
                    "name": source_name,
                    "original_price_q": price_q,
                    "discount_q": best_discount_q,
                    "qty": qty,
                })
                if source_type == "coupon":
                    total_coupon_discount_q += best_discount_q * qty

        if modified:
            session.update_items(items)

        # Persist discount info in session.pricing (items lose extra fields on save)
        if not session.pricing:
            session.pricing = {}
        session.pricing["discount"] = {
            "total_discount_q": sum(d["discount_q"] * d["qty"] for d in discounts_applied),
            "items": discounts_applied,
        }
        if coupon_code:
            session.pricing["coupon"] = {
                "code": coupon_code,
                "discount_q": total_coupon_discount_q,
            }
        else:
            session.pricing.pop("coupon", None)

    @staticmethod
    def _matches(promo: Any, sku: str, ctx: dict) -> bool:
        if promo.fulfillment_types:
            fulfillment_type = (ctx.get("fulfillment_type") or "").strip()
            if fulfillment_type:
                if fulfillment_type not in promo.fulfillment_types:
                    return False
            else:
                # Sessão ainda sem tipo (antes do checkout): mesma regra da vitrine
                # (`_promo_matches_for_vitrine`) — aceita se *algum* tipo permitido pela
                # promo fizer match. Caso contrário, promo só-delivery nunca aplicaria no
                # carrinho e o cardápio mostraria R$ 2 off enquanto o carrinho só 15%.
                for try_ft in promo.fulfillment_types:
                    c = {**ctx, "fulfillment_type": try_ft}
                    if DiscountModifier._matches(promo, sku, c):
                        return True
                return False
        if promo.skus and sku not in promo.skus:
            return False
        if promo.collections:
            item_collections = ctx.get("sku_collections", {}).get(sku, [])
            if not any(c in promo.collections for c in item_collections):
                return False
        if promo.customer_segments:
            customer_segment = ctx.get("customer_segment", "")
            customer_group = ctx.get("customer_group", "")
            if customer_segment not in promo.customer_segments and customer_group not in promo.customer_segments:
                return False
        return True

    @staticmethod
    def _calc_discount(promo: Any, price_q: int) -> int:
        if promo.type == "percent":
            return monetary_div(price_q * promo.value, 100)
        return min(promo.value, price_q)



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
        modified = False
        for item in items:
            original_q = item.get("unit_price_q", 0)
            discount_q = monetary_div(original_q * EMPLOYEE_DISCOUNT_PERCENT, 100)
            item["unit_price_q"] = original_q - discount_q
            item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))
            item.setdefault("modifiers_applied", []).append(
                {"type": "employee_discount", "discount_percent": EMPLOYEE_DISCOUNT_PERCENT}
            )
            modified = True

        if modified:
            session.update_items(items)
            total_discount_q = sum(
                monetary_div(item.get("unit_price_q", 0) * EMPLOYEE_DISCOUNT_PERCENT, 100 - EMPLOYEE_DISCOUNT_PERCENT)
                * int(item.get("qty", 1))
                for item in items
                if any(m.get("type") == "employee_discount" for m in item.get("modifiers_applied", []))
            )
            pricing = session.pricing or {}
            if total_discount_q > 0:
                pricing["employee_discount"] = {"total_discount_q": total_discount_q, "label": "Desconto funcionário"}
            else:
                pricing.pop("employee_discount", None)
            session.pricing = pricing
            session.save(update_fields=["pricing"])


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
        start: time | None = None,
        end: time | None = None,
    ):
        self.discount_percent = discount_percent

        if start is None:
            raw = getattr(settings, "SHOPMAN_HAPPY_HOUR_START", "16:00")
            h, m = map(int, raw.split(":"))
            start = time(h, m)
        if end is None:
            raw = getattr(settings, "SHOPMAN_HAPPY_HOUR_END", "18:00")
            h, m = map(int, raw.split(":"))
            end = time(h, m)

        self.start = start
        self.end = end

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        # Vitrine não inclui happy hour no preço exibido; aplicar HH só no web geraria
        # divergência (ex.: card 5,50 vs carrinho ~5,73). HH permanece para POS/outros.
        if (session.data or {}).get("origin_channel") == "web":
            return

        now = timezone.localtime().time()
        if not (self.start <= now < self.end):
            return

        items = session.items or []
        modified = False
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
            modified = True

        if modified:
            session.update_items(items)
            total_discount_q = sum(
                monetary_div(item.get("unit_price_q", 0) * self.discount_percent, 100 - self.discount_percent)
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


class DeliveryFeeModifier:
    """
    Taxa de entrega calculada por zona (DeliveryZone).

    Só se aplica quando fulfillment_type == "delivery".
    Lê postal_code e neighborhood de session.data["delivery_address_structured"].
    Busca a DeliveryZone ativa de maior prioridade que coincide com o endereço.

    Se nenhuma zona coincidir → seta session.data["delivery_zone_error"] = True.
    Se zona encontrada → seta session.data["delivery_fee_q"] = zone.fee_q.
    fee_q == 0 → entrega grátis (sem erro).
    """

    code = "shop.delivery_fee"
    order = 70

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shopman.models import DeliveryZone

        data = session.data or {}
        fulfillment_type = data.get("fulfillment_type", "")
        if fulfillment_type != "delivery":
            return

        addr_structured = data.get("delivery_address_structured") or {}
        postal_code = (addr_structured.get("postal_code") or "").strip()
        neighborhood = (addr_structured.get("neighborhood") or "").strip()

        if not postal_code and not neighborhood:
            # Endereço ainda não preenchido (pré-checkout) — não calcular taxa
            return

        zone = DeliveryZone.match(postal_code=postal_code, neighborhood=neighborhood)

        if zone is None:
            # Endereço fora da área de entrega
            new_data = {**data, "delivery_zone_error": True}
            new_data.pop("delivery_fee_q", None)
            session.data = new_data
            session.save(update_fields=["data"])
            return

        # Zona encontrada — gravar taxa e limpar eventual erro anterior
        new_data = {**data, "delivery_fee_q": zone.fee_q}
        new_data.pop("delivery_zone_error", None)
        session.data = new_data
        session.save(update_fields=["data"])
