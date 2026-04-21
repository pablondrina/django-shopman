"""
Storefront device management views (HTMX).

Lists trusted devices and allows revoking them.
"""

from __future__ import annotations

import logging
import uuid

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from ..constants import HAS_AUTH

logger = logging.getLogger("shopman.storefront.views.devices")


def _geolocate_ip(ip: str) -> str:
    """Resolve IP to city/region via ip-api.com (cached 24h). Returns '' on failure."""
    if not ip or ip.startswith("127.") or ip.startswith("10.") or ip == "::1":
        return ""
    cache_key = f"geo:{ip}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    try:
        import json
        import urllib.request

        url = f"http://ip-api.com/json/{ip}?fields=city,regionName,country&lang=pt-BR"
        with urllib.request.urlopen(url, timeout=2) as resp:
            data = json.loads(resp.read())
        if data.get("city"):
            location = f"{data['city']}, {data.get('regionName', '')}"
            cache.set(cache_key, location, 86400)
            return location
    except Exception:
        logger.exception("geolocate_ip_failed ip=%s", ip)
    cache.set(cache_key, "", 3600)  # Cache failures for 1h
    return ""


def _get_customer_id(request: HttpRequest) -> uuid.UUID | None:
    """Extract customer_id from authenticated request."""
    customer_info = getattr(request, "customer", None)
    if customer_info is not None:
        return customer_info.uuid
    return None


class DeviceListView(View):
    """Render device list partial for the account page."""

    def get(self, request: HttpRequest) -> HttpResponse:
        if not HAS_AUTH:
            return HttpResponse("")

        customer_id = _get_customer_id(request)
        if customer_id is None:
            return HttpResponse('<p class="text-bark-light text-sm">Faça login para ver seus dispositivos.</p>')

        from shopman.doorman import TrustedDevice, hash_device_token
        from shopman.doorman.conf import doorman_settings

        devices = TrustedDevice.objects.filter(
            customer_id=customer_id,
            is_active=True,
        ).order_by("-last_used_at", "-created_at")

        # Check which is the current device
        raw_token = request.COOKIES.get(doorman_settings.DEVICE_TRUST_COOKIE_NAME)
        current_hash = hash_device_token(raw_token) if raw_token else None

        device_list = []
        for d in devices:
            if d.is_valid:
                location = _geolocate_ip(d.ip_address) if d.ip_address else ""
                device_list.append({
                    "id": str(d.id),
                    "label": d.label.replace(" / ", " no ") if d.label else "",
                    "created_at": d.created_at,
                    "last_used_at": d.last_used_at,
                    "location": location,
                    "is_current": current_hash is not None and d.token_hash == current_hash,
                })

        return render(request, "storefront/partials/device_list.html", {
            "devices": device_list,
        })


class DeviceRevokeView(View):
    """Revoke a specific device (DELETE via HTMX)."""

    def delete(self, request: HttpRequest, device_id: str) -> HttpResponse:
        if not HAS_AUTH:
            return HttpResponse("")

        customer_id = _get_customer_id(request)
        if customer_id is None:
            return HttpResponse('<p class="text-sm text-error">Autenticação necessária.</p>')

        from shopman.doorman import TrustedDevice

        try:
            device_uuid = uuid.UUID(str(device_id))
        except ValueError:
            return HttpResponse('<p class="text-sm text-error">ID inválido.</p>')

        try:
            device = TrustedDevice.objects.get(
                id=device_uuid,
                customer_id=customer_id,
                is_active=True,
            )
        except TrustedDevice.DoesNotExist:
            return HttpResponse("")  # Already gone

        device.revoke()
        logger.info("Device revoked from storefront", extra={"device_id": str(device.id)})

        # Return empty to remove the element from DOM
        return HttpResponse("")


class DeviceRevokeAllView(View):
    """Revoke all devices for the customer (DELETE via HTMX)."""

    def delete(self, request: HttpRequest) -> HttpResponse:
        if not HAS_AUTH:
            return HttpResponse("")

        customer_id = _get_customer_id(request)
        if customer_id is None:
            return HttpResponse('<p class="text-sm text-error">Autenticação necessária.</p>')

        from shopman.doorman.conf import doorman_settings
        from shopman.doorman.services.device_trust import DeviceTrustService

        count = DeviceTrustService.revoke_all(customer_id)

        response = HttpResponse(
            '<p class="text-bark-light text-sm text-center py-4">Todos os dispositivos foram revogados.</p>'
        )
        response.delete_cookie(doorman_settings.DEVICE_TRUST_COOKIE_NAME)

        logger.info(
            "All devices revoked from storefront",
            extra={"customer_id": str(customer_id), "count": count},
        )

        return response
