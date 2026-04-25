"""Availability API endpoint — public, no auth, cached."""

from __future__ import annotations

from decimal import Decimal

from django.core.cache import cache
from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import availability as avail_service
from shopman.storefront.services import catalog as catalog_service


class AvailabilityView(APIView):
    """
    GET /api/v1/availability/<sku>/?channel=<channel_ref>

    Returns the current availability status for a SKU, optionally scoped
    to a channel (listing gate + channel-specific stock scope).

    Response:
        {
            "ok": bool,
            "available_qty": str,   # Decimal as string
            "badge_text": str,      # Human-readable label (pt-BR)
            "badge_class": str,     # CSS class for badge rendering
            "is_bundle": bool,
        }

    Cache TTL: 10 seconds per (sku, channel_ref).
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request, sku):
        if not catalog_service.product_exists(sku):
            raise Http404

        channel_ref = request.GET.get("channel")
        cache_key = f"availability:{sku}:{channel_ref or 'default'}"

        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        result = avail_service.check(sku, Decimal("1"), channel_ref=channel_ref)

        badge_text, badge_class = _badge_for(result)

        data = {
            "ok": result["ok"],
            "available_qty": str(result["available_qty"]),
            "badge_text": badge_text,
            "badge_class": badge_class,
            "is_bundle": result.get("is_bundle", False),
        }

        cache.set(cache_key, data, 10)
        return Response(data)


def _badge_for(result: dict) -> tuple[str, str]:
    """Derive Portuguese badge text and CSS class from an availability result.

    Vocabulário canônico (AVAILABILITY-PLAN §2): qualquer estado que não seja
    "pode pedir agora" vira "Indisponível" — um único rótulo.
    """
    if result["ok"]:
        return "Disponível", "badge-available"
    return "Indisponível", "badge-unavailable"
