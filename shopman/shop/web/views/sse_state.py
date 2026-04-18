"""Per-SKU availability state partial — feeds the SSE refresh swap.

Returns the canonical badge HTML and emits a ``sku-state`` HX-Trigger event
carrying the full state payload (``available_qty``, ``can_add``, ``availability``).
Cards listen for the trigger to keep their Alpine state (max, can_add) in sync
without a second fetch.
"""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views import View
from shopman.offerman.models import Product

from shopman.shop.config import ChannelConfig
from shopman.shop.projections.types import (
    AVAILABILITY_LABELS_PT,
    Availability,
)

logger = logging.getLogger(__name__)


class SkuStateView(View):
    """Render the availability badge for a single SKU.

    GET /storefront/sku/<sku>/state/?channel_ref=web

    Response: HTML fragment (the badge ``<span>``) plus an ``HX-Trigger``
    header carrying the full state so client Alpine components can update
    derived UI (stepper max, add-to-cart enable/disable) without a second
    request.
    """

    def get(self, request: HttpRequest, sku: str) -> HttpResponse:
        product = get_object_or_404(Product, sku=sku)

        channel_ref = (
            request.GET.get("channel_ref")
            or getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")
        )

        availability, available_qty, can_add = _resolve_state(
            product=product,
            channel_ref=channel_ref,
        )

        response = render(
            request,
            "storefront/components/availability_badge.html",
            {"state": availability.value},
        )
        response["HX-Trigger"] = json.dumps(
            {
                "sku-state": {
                    "sku": sku,
                    "channel_ref": channel_ref,
                    "availability": availability.value,
                    "available_qty": available_qty,
                    "can_add_to_cart": can_add,
                    "label": AVAILABILITY_LABELS_PT[availability],
                }
            }
        )
        return response


def _resolve_state(
    *, product: Product, channel_ref: str
) -> tuple[Availability, int | None, bool]:
    """Compute the canonical state tuple for this SKU on this channel.

    Mirrors :func:`shopman.shop.projections.catalog._resolve_availability` so
    the badge rendered by SSE refresh matches what a fresh menu render would
    show. Kept inline to avoid coupling this view to projection internals.
    """
    config = ChannelConfig.for_channel(channel_ref)
    low_stock_threshold = Decimal(str(config.stock.low_stock_threshold))

    raw_avail: dict | None
    try:
        from shopman.stockman.services.availability import availability_for_skus

        from shopman.shop.adapters import stock as stock_adapter

        scope = stock_adapter.get_channel_scope(channel_ref)
        avail_map = availability_for_skus(
            [product.sku],
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
            excluded_positions=scope.get("excluded_positions"),
        )
        raw_avail = avail_map.get(product.sku)
    except Exception:
        logger.warning(
            "SkuStateView: availability lookup failed sku=%s channel=%s",
            product.sku, channel_ref, exc_info=True,
        )
        raw_avail = None

    if not product.is_sellable:
        return Availability.UNAVAILABLE, 0, False

    if raw_avail is None:
        return Availability.AVAILABLE, None, True

    if raw_avail.get("is_paused", False):
        return Availability.UNAVAILABLE, 0, False

    policy = raw_avail.get("availability_policy", "planned_ok")
    total_promisable = raw_avail.get("total_promisable") or Decimal("0")
    if not isinstance(total_promisable, Decimal):
        total_promisable = Decimal(str(total_promisable))

    if policy == "demand_ok":
        return Availability.AVAILABLE, None, True

    if total_promisable <= 0:
        if policy == "planned_ok" and raw_avail.get("is_planned", False):
            return Availability.PLANNED_OK, 0, True
        return Availability.UNAVAILABLE, 0, False

    available_qty = int(total_promisable)
    if total_promisable <= low_stock_threshold:
        return Availability.LOW_STOCK, available_qty, True

    return Availability.AVAILABLE, available_qty, True
