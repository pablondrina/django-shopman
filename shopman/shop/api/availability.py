"""Availability API endpoint — public, no auth, cached."""

from __future__ import annotations

from decimal import Decimal

from django.core.cache import cache
from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.offerman.models import Product
from shopman.shop.services import availability as avail_service


class AvailabilityView(APIView):
    """
    GET /api/availability/<sku>/?channel=<channel_ref>

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
        if not Product.objects.filter(sku=sku).exists():
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
    """Derive Portuguese badge text and CSS class from an availability result."""
    if result["ok"]:
        return "Disponível", "badge-available"
    code = result.get("error_code", "")
    if code == "insufficient_stock":
        return "Esgotado", "badge-sold-out"
    if code == "below_min_qty":
        qty = result.get("available_qty", "")
        return f"Mín. {qty} un.", "badge-min-qty"
    return "Indisponível", "badge-unavailable"
