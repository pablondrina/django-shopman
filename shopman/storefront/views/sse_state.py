"""Per-SKU availability state partial — feeds the SSE refresh swap.

Returns the canonical badge HTML and emits a ``sku-state`` HX-Trigger event
carrying the full state payload (``available_qty``, ``can_add``, ``availability``).
Cards listen for the trigger to keep their Alpine state (max, can_add) in sync
without a second fetch.
"""

from __future__ import annotations

import json

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from shopman.storefront.services import sku_state as sku_state_service


class SkuStateView(View):
    """Render the availability badge for a single SKU.

    GET /storefront/sku/<sku>/state/?channel_ref=web

    Response: HTML fragment (the badge ``<span>``) plus an ``HX-Trigger``
    header carrying the full state so client Alpine components can update
    derived UI (stepper max, add-to-cart enable/disable) without a second
    request.
    """

    def get(self, request: HttpRequest, sku: str) -> HttpResponse:
        channel_ref = (
            request.GET.get("channel_ref")
            or getattr(settings, "SHOPMAN_STOREFRONT_CHANNEL_REF", "web")
        )
        sku_state = sku_state_service.resolve(sku=sku, channel_ref=channel_ref)

        response = render(
            request,
            "storefront/components/availability_badge.html",
            {"state": sku_state.availability.value},
        )
        response["HX-Trigger"] = json.dumps(
            {
                "sku-state": {
                    "sku": sku_state.sku,
                    "channel_ref": channel_ref,
                    "availability": sku_state.availability.value,
                    "available_qty": sku_state.available_qty,
                    "can_add_to_cart": sku_state.can_add_to_cart,
                    "label": sku_state.label,
                }
            }
        )
        return response
