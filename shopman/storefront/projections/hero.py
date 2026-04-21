from __future__ import annotations

import logging

from django.http import HttpRequest
from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.storefront.services.storefront_context import popular_skus, session_pricing_hints

logger = logging.getLogger(__name__)


def _hero_data(listing_ref: str | None = None, request: HttpRequest | None = None) -> dict | None:
    """Build hero section data: featured promotion or most popular product.

    Returns dict with keys: product, price_display, promo, image_url, badge
    or None if no suitable hero found.
    """
    from shopman.storefront.views._helpers import _best_auto_promotion_discount_q, _get_price_q

    try:
        from shopman.storefront.models import Promotion

        now = timezone.now()
        promo = (
            Promotion.objects.filter(
                is_active=True,
                valid_from__lte=now,
                valid_until__gte=now,
            )
            .order_by("-valid_from")
            .first()
        )

        if promo and promo.skus:
            from shopman.offerman.models import Product as Prod

            product = Prod.objects.filter(sku=promo.skus[0], is_published=True).first()
            if product:
                price_q = _get_price_q(product, listing_ref=listing_ref)
                if promo.type == "percent":
                    discount_label = f"{promo.value}% OFF"
                else:
                    discount_label = f"R$ {format_money(promo.value)} OFF"
                cols: list[str] = []
                try:
                    from shopman.offerman.models import CollectionItem

                    cols = list(
                        CollectionItem.objects.filter(product=product).values_list(
                            "collection__ref", flat=True,
                        ),
                    )
                except Exception as e:
                    logger.warning("hero_data_collections_failed: %s", e, exc_info=True)
                    cols = []
                ft_hint, sub_hint = session_pricing_hints(request)
                disc_q, _ = _best_auto_promotion_discount_q(
                    promo.skus[0],
                    price_q or 0,
                    cols,
                    session_total_q=sub_hint,
                    fulfillment_type=ft_hint,
                )
                eff_q = (price_q or 0) - disc_q if price_q else None
                return {
                    "product": product,
                    "price_display": f"R$ {format_money(eff_q)}" if eff_q else None,
                    "original_price_display": f"R$ {format_money(price_q)}" if disc_q and price_q else None,
                    "promo_name": promo.name,
                    "discount_label": discount_label,
                    "image_url": product.image_url,
                    "sku": product.sku,
                }

        # Fallback: most popular product
        pop = popular_skus(limit=1)
        if pop:
            from shopman.offerman.models import Product as Prod

            sku = next(iter(pop))
            product = Prod.objects.filter(sku=sku, is_published=True).first()
            if product:
                price_q = _get_price_q(product, listing_ref=listing_ref)
                return {
                    "product": product,
                    "price_display": f"R$ {format_money(price_q)}" if price_q else None,
                    "promo_name": None,
                    "discount_label": None,
                    "image_url": product.image_url,
                    "sku": product.sku,
                }
    except Exception as e:
        logger.warning("hero_data_failed: %s", e, exc_info=True)
    return None
