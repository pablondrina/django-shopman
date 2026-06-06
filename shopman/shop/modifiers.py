"""
Shop — Custom order modifiers.

Modifiers follow the Orderman Modifier protocol:
- code: str — unique identifier
- order: int — execution order (lower = first)
- apply(*, channel, session, ctx) -> None — mutates session in-place

Execution order:
  10  pricing.item          — base price from backend (qty-aware)
  20  shop.discount         — promotions + coupons (maior desconto ganha)
  50  pricing.session_total — recalculate total
  60  shop.employee_discount
  70  shop.delivery_fee     — taxa de entrega por zona (só delivery)
  80  shop.loyalty_redeem   — loyalty points redemption (post-pricing)
  85  shop.manual_discount  — desconto manual (POS)

Rule-driven discount modifiers (availability / time-window) are generic and
configured per deployment through ``RuleConfig`` rows — enabled state, params and
channel scope all live in the DB. They are registered unconditionally; execution
is gated by ``get_channel_rule_params`` so a disabled rule means no discount.

Discount policy — "maior desconto ganha":
  Per item, only ONE discount applies (the best one).
  Employee discount is post-pricing.
"""
from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone
from shopman.utils.monetary import monetary_div

logger = logging.getLogger(__name__)

# ── Configurable defaults ──────────────────────────────────────────
DEFAULT_EMPLOYEE_DISCOUNT_PERCENT = 20
DEFAULT_AVAILABILITY_DISCOUNT_PERCENT = 50


def _is_non_merchandise_line(item: dict) -> bool:
    meta = item.get("meta") or {}
    return item.get("sku") == "__DELIVERY_FEE__" or meta.get("type") in {"delivery_fee"}


def _discount_label(copy_key: str, fallback: str) -> str:
    """Resolve a customer-facing discount label from OmotenashiCopy.

    The label is moment/audience-agnostic, so the wildcard cascade resolves the
    deployment override (if any) or the generic code default. ``fallback`` is the
    last resort if the key is unknown.
    """
    from shopman.shop.omotenashi.copy import WILDCARD, resolve_copy

    entry = resolve_copy(copy_key, moment=WILDCARD, audience=WILDCARD)
    return entry.title or entry.message or fallback


class AvailabilityDiscountModifier:
    """Discount applied to lines flagged as limited-availability stock.

    Generic form of the "day-old / last-units" clearance discount: when a line
    is flagged ``is_d1`` (either on the item or in ``session.data["availability"]``)
    it receives a percentage off. Rule-driven — params and channel scope come
    from the ``d1_discount`` RuleConfig; a disabled rule means no discount.
    """

    code = "shop.d1_discount"
    order = 15

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shopman.shop.rules.engine import get_channel_rule_params

        availability = (session.data or {}).get("availability", {})
        items = session.items or []
        if not any(
            item.get("is_d1", False)
            or availability.get(item.get("sku", ""), {}).get("is_d1", False)
            for item in items
        ):
            return

        params = get_channel_rule_params("d1_discount", getattr(channel, "ref", None))
        if params is None:
            return
        percent = params.get("discount_percent", DEFAULT_AVAILABILITY_DISCOUNT_PERCENT)

        modified = False
        for item in items:
            if _is_non_merchandise_line(item):
                continue
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
                pricing["d1_discount"] = {
                    "total_discount_q": total_discount_q,
                    "label": _discount_label("CART_DISCOUNT_LABEL_AVAILABILITY", "Liquidação"),
                }
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

    Promoções com ``fulfillment_types`` só se aplicam depois que o cliente escolhe o tipo
    de entrega no checkout. Sem ``fulfillment_type`` na sessão → desconto não aplica.
    """

    code = "shop.discount"
    order = 20

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        from shopman.shop.adapters import get_adapter

        # Inject fulfillment_type from session data into ctx for matching
        fulfillment_type = (session.data or {}).get("fulfillment_type", "")
        if fulfillment_type:
            ctx.setdefault("fulfillment_type", fulfillment_type)

        # Inject is_birthday — needed for birthday_only promotions
        if "is_birthday" not in ctx:
            customer_ref = (session.data or {}).get("customer", {}).get("ref")
            if customer_ref:
                try:
                    from shopman.guestman.models import Customer
                    customer = Customer.objects.filter(ref=customer_ref).only("birthday").first()
                    if customer and customer.birthday:
                        today = timezone.localdate()
                        ctx["is_birthday"] = (
                            customer.birthday.month == today.month
                            and customer.birthday.day == today.day
                        )
                except Exception:
                    logger.debug(
                        "discount_modifier: birthday lookup failed for customer=%s",
                        customer_ref,
                        exc_info=True,
                    )

        now = timezone.now()

        adapter = get_adapter("promotion")
        promotions = adapter.get_active_promotions(now) if adapter else []

        coupon_code = (session.data or {}).get("coupon_code")
        coupon_promo = None
        if coupon_code and adapter:
            coupon_promo = adapter.get_coupon_promotion(coupon_code, now)

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
                from shopman.offerman.models import CollectionItem

                line_skus = [i.get("sku") for i in items if i.get("sku") and not _is_non_merchandise_line(i)]
                col_map: dict[str, list[str]] = {}
                for ci in CollectionItem.objects.filter(product__sku__in=line_skus).select_related(
                    "collection",
                ):
                    col_map.setdefault(ci.product.sku, []).append(ci.collection.ref)
                ctx["sku_collections"] = col_map
            except Exception:
                logger.debug(
                    "discount_modifier: collection lookup failed for skus=%s",
                    line_skus,
                    exc_info=True,
                )

        session_total = sum(item.get("line_total_q", 0) for item in items if not _is_non_merchandise_line(item))
        modified = False
        total_coupon_discount_q = 0
        discounts_applied = []  # Persisted in session.pricing

        for item in items:
            if _is_non_merchandise_line(item):
                continue
            sku = item.get("sku", "")
            price_q = item.get("unit_price_q", 0)
            if not price_q:
                continue

            # D-1 items skip auto promos. A manager-approved manual discount may
            # still apply to a D-1 line (audited exception); a plain operator
            # manual discount on a non-D-1 line competes under "best wins".
            applied = item.get("modifiers_applied", [])
            is_d1_line = any(m.get("type") == "d1_discount" for m in applied)
            manual = (item.get("meta") or {}).get("manual_discount") or {}
            manual_allowed = bool(
                manual.get("value")
                and (not is_d1_line or manual.get("approved_by"))
            )
            if is_d1_line and not manual_allowed:
                continue

            # Find best discount candidate
            best_discount_q = 0
            best_source = None  # (type, name)

            # Auto-promotions and coupon do not apply to D-1 lines.
            if not is_d1_line:
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

            # Evaluate operator manual per-line discount (percent), best wins.
            if manual_allowed:
                manual_discount_q = self._calc_manual(manual, price_q)
                if manual_discount_q > best_discount_q:
                    best_discount_q = manual_discount_q
                    best_source = ("manual", manual.get("reason") or "manual", None)

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
                # fulfillment_type not chosen yet — don't pre-apply fulfillment-restricted promos
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
        if getattr(promo, "birthday_only", False):
            if not ctx.get("is_birthday"):
                return False
        return True

    @staticmethod
    def _calc_discount(promo: Any, price_q: int) -> int:
        if promo.type == "percent":
            return monetary_div(price_q * promo.value, 100)
        return min(promo.value, price_q)

    @staticmethod
    def _calc_manual(manual: dict, price_q: int) -> int:
        """Per-unit discount from an operator manual line discount (percent only)."""
        try:
            value = float(manual.get("value") or 0)
        except (TypeError, ValueError):
            return 0
        if value <= 0:
            return 0
        return min(monetary_div(int(round(price_q * value)), 100), price_q)



class EmployeeDiscountModifier:
    """
    Discount for employees (customer_group == "staff").

    Percentage is configurable via channel config rules.employee_discount_percent
    or SHOPMAN_EMPLOYEE_DISCOUNT_PERCENT setting (default 20).

    Applied per-item. Adjusts unit_price_q and line_total_q on session.items.
    """

    code = "shop.employee_discount"
    order = 60  # After canonical pricing (10, 50), before session total recalc

    def __init__(self, *, discount_percent: int = DEFAULT_EMPLOYEE_DISCOUNT_PERCENT):
        self.discount_percent = discount_percent

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        customer_group = (session.data or {}).get("customer", {}).get("group", "")
        if customer_group != "staff":
            return

        config = getattr(channel, "config", None) or {}
        channel_rules = config.get("rules", {})
        if "employee_discount_percent" in channel_rules:
            percent = channel_rules["employee_discount_percent"]
        else:
            from shopman.shop.rules.engine import get_rule_params
            percent = get_rule_params("employee_discount").get("discount_percent", self.discount_percent)

        items = session.items or []
        modified = False
        for item in items:
            if _is_non_merchandise_line(item):
                continue
            original_q = item.get("unit_price_q", 0)
            discount_q = monetary_div(original_q * percent, 100)
            item["unit_price_q"] = original_q - discount_q
            item["line_total_q"] = item["unit_price_q"] * int(item.get("qty", 1))
            item.setdefault("modifiers_applied", []).append(
                {"type": "employee_discount", "discount_percent": percent}
            )
            modified = True

        if modified:
            session.update_items(items)
            total_discount_q = sum(
                monetary_div(item.get("unit_price_q", 0) * percent, 100 - percent)
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
        from shopman.shop.adapters import get_adapter

        data = session.data or {}
        fulfillment_type = data.get("fulfillment_type", "")
        if fulfillment_type != "delivery":
            return

        if data.get("delivery_fee_q") not in (None, ""):
            if data.get("delivery_zone_error"):
                new_data = {**data}
                new_data.pop("delivery_zone_error", None)
                session.data = new_data
                session.save(update_fields=["data"])
            return

        addr_structured = data.get("delivery_address_structured") or {}
        postal_code = (addr_structured.get("postal_code") or "").strip()
        neighborhood = (addr_structured.get("neighborhood") or "").strip()

        if not postal_code and not neighborhood:
            # Endereço ainda não preenchido (pré-checkout) — não calcular taxa
            return

        adapter = get_adapter("promotion")
        if adapter is None:
            return
        zone = adapter.match_delivery_zone(postal_code, neighborhood)

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


class LoyaltyRedeemModifier:
    """
    Apply loyalty points redemption as a discount.

    Reads session.data["loyalty"]["redeem_points_q"] (centavos to redeem).
    Clamps to min(balance, subtotal) to never make total negative.
    Writes discount summary to session.pricing["loyalty_redeem"].
    """

    code = "shop.loyalty_redeem"
    order = 80  # After all other discounts and delivery fee

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        loyalty_data = (session.data or {}).get("loyalty", {})
        redeem_q = int(loyalty_data.get("redeem_points_q", 0))
        if redeem_q <= 0:
            pricing = session.pricing or {}
            if "loyalty_redeem" in pricing:
                pricing.pop("loyalty_redeem", None)
                session.pricing = pricing
                session.save(update_fields=["pricing"])
            return

        items = session.items or []
        subtotal_q = sum(item.get("line_total_q", 0) for item in items if not _is_non_merchandise_line(item))

        # Clamp: never redeem more than the order total
        redeem_q = min(redeem_q, subtotal_q)
        if redeem_q <= 0:
            return

        # Distribute the redemption proportionally across items
        remaining = redeem_q
        modified = False
        for i, item in enumerate(items):
            if _is_non_merchandise_line(item):
                continue
            line_total = item.get("line_total_q", 0)
            if line_total <= 0:
                continue
            is_last = i == len(items) - 1
            if is_last:
                item_share = remaining
            else:
                item_share = monetary_div(redeem_q * line_total, subtotal_q)
            item_share = min(item_share, line_total)
            if item_share > 0:
                qty = int(item.get("qty", 1)) or 1
                per_unit = item_share // qty
                item["unit_price_q"] = max(0, item.get("unit_price_q", 0) - per_unit)
                item["line_total_q"] = max(0, line_total - item_share)
                remaining -= item_share
                modified = True

        if modified:
            session.update_items(items)

        # Persist for cart transparency
        pricing = session.pricing or {}
        pricing["loyalty_redeem"] = {
            "total_discount_q": redeem_q,
            "label": "Resgate de pontos",
        }
        session.pricing = pricing
        session.save(update_fields=["pricing"])


class ManualDiscountModifier:
    """
    Desconto manual aplicado pelo operador no POS.

    Lê session.data["manual_discount"]["discount_q"] (centavos) e
    session.data["manual_discount"]["reason"] (motivo).
    Aplica proporcionalmentenos itens e persiste em session.pricing["manual_discount"].

    Ordem 85: após loyalty (80), só POS usa este modifier.
    """

    code = "shop.manual_discount"
    order = 85

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        manual = (session.data or {}).get("manual_discount") or {}
        discount_q = int(manual.get("discount_q", 0))
        reason = str(manual.get("reason", "") or "")

        pricing = session.pricing or {}

        if discount_q <= 0:
            if "manual_discount" in pricing:
                pricing.pop("manual_discount", None)
                session.pricing = pricing
                session.save(update_fields=["pricing"])
            return

        items = session.items or []
        subtotal_q = sum(item.get("line_total_q", 0) for item in items if not _is_non_merchandise_line(item))
        discount_q = min(discount_q, subtotal_q)
        if discount_q <= 0:
            return

        remaining = discount_q
        modified = False
        for i, item in enumerate(items):
            if _is_non_merchandise_line(item):
                continue
            line_total = item.get("line_total_q", 0)
            if line_total <= 0:
                continue
            is_last = i == len(items) - 1
            if is_last:
                item_share = remaining
            else:
                item_share = monetary_div(discount_q * line_total, subtotal_q)
            item_share = min(item_share, line_total)
            if item_share > 0:
                qty = int(item.get("qty", 1)) or 1
                per_unit = item_share // qty
                item["unit_price_q"] = max(0, item.get("unit_price_q", 0) - per_unit)
                item["line_total_q"] = max(0, line_total - item_share)
                remaining -= item_share
                modified = True

        if modified:
            session.update_items(items)

        pricing["manual_discount"] = {
            "total_discount_q": discount_q,
            "label": f"Desconto ({reason})" if reason else "Desconto manual",
        }
        session.pricing = pricing
        session.save(update_fields=["pricing"])
