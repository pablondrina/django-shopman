from __future__ import annotations

from decimal import Decimal

from django.utils import timezone

from shopman.shop.models import Promotion
from shopman.shop.modifiers import DiscountModifier
from shopman.offerman.protocols import ContextualPrice, PriceAdjustment
from shopman.utils.monetary import format_money


class StorefrontPricingBackend:
    """
    Contextual pricing backend for the framework storefront.

    Offerman remains the source of list prices and channel tiers. This backend
    only projects the framework's automatic promotion logic into the canonical
    ContextualPrice contract.
    """

    def get_price(
        self,
        *,
        sku: str,
        qty: Decimal,
        listing: str | None,
        list_unit_price_q: int,
        list_total_price_q: int,
        context: dict | None = None,
    ) -> ContextualPrice:
        context = context or {}
        sku_collections = context.get("sku_collections") or []
        fulfillment_type = context.get("fulfillment_type") or ""
        session_total_q = int(context.get("session_total_q") or 0)
        customer_segment = context.get("customer_segment") or ""
        customer_group = context.get("customer_group") or ""

        best_discount_q = 0
        best_promo = None

        now = timezone.now()
        promotions = list(
            Promotion.objects.filter(
                is_active=True,
                valid_from__lte=now,
                valid_until__gte=now,
            ).exclude(coupons__isnull=False)
        )

        match_ctx = {
            "fulfillment_type": fulfillment_type,
            "sku_collections": {sku: sku_collections},
            "customer_segment": customer_segment,
            "customer_group": customer_group,
        }

        for promo in promotions:
            if promo.min_order_q and session_total_q < promo.min_order_q:
                continue
            if not DiscountModifier._matches(promo, sku, match_ctx):
                continue
            discount_q = DiscountModifier._calc_discount(promo, list_unit_price_q)
            if discount_q > best_discount_q:
                best_discount_q = discount_q
                best_promo = promo

        if best_promo is None or best_discount_q <= 0:
            return ContextualPrice(
                sku=sku,
                qty=qty,
                listing=listing,
                list_unit_price_q=list_unit_price_q,
                list_total_price_q=list_total_price_q,
                final_unit_price_q=list_unit_price_q,
                final_total_price_q=list_total_price_q,
                adjustments=[],
                metadata={"source": "framework.storefront_pricing"},
            )

        total_discount_q = int(best_discount_q * qty)
        final_unit_price_q = max(list_unit_price_q - best_discount_q, 0)
        final_total_price_q = max(list_total_price_q - total_discount_q, 0)
        if best_promo.type == Promotion.PERCENT:
            badge_label = f"-{best_promo.value}%"
        else:
            badge_label = f"-R$ {format_money(best_promo.value)}"

        return ContextualPrice(
            sku=sku,
            qty=qty,
            listing=listing,
            list_unit_price_q=list_unit_price_q,
            list_total_price_q=list_total_price_q,
            final_unit_price_q=final_unit_price_q,
            final_total_price_q=final_total_price_q,
            adjustments=[
                PriceAdjustment(
                    code="promotion",
                    label=best_promo.name,
                    amount_q=total_discount_q,
                    metadata={
                        "promotion_name": best_promo.name,
                        "promotion_type": best_promo.type,
                        "promotion_value": best_promo.value,
                        "badge_label": badge_label,
                        "unit_discount_q": best_discount_q,
                    },
                )
            ],
            metadata={"source": "framework.storefront_pricing"},
        )
