"""
Storefront device management views (HTMX).

Lists trusted devices and allows revoking them.
"""

from __future__ import annotations

import uuid

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from ..constants import HAS_AUTH
from ..services import devices as device_service


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

        devices = device_service.list_devices(
            customer_id=customer_id,
            raw_token=request.COOKIES.get(device_service.cookie_name()),
        )

        return render(request, "storefront/partials/device_list.html", {
            "devices": devices,
        })


class DeviceRevokeView(View):
    """Revoke a specific device (DELETE via HTMX)."""

    def delete(self, request: HttpRequest, device_id: str) -> HttpResponse:
        if not HAS_AUTH:
            return HttpResponse("")

        customer_id = _get_customer_id(request)
        if customer_id is None:
            return HttpResponse('<p class="text-sm text-error">Autenticação necessária.</p>')

        error = device_service.revoke_device(
            customer_id=customer_id,
            device_id=device_id,
        )
        if error:
            return HttpResponse(f'<p class="text-sm text-error">{error}</p>')

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

        device_service.revoke_all(customer_id=customer_id)

        response = HttpResponse(
            '<p class="text-bark-light text-sm text-center py-4">Todos os dispositivos foram revogados.</p>'
        )
        response.delete_cookie(device_service.cookie_name())

        return response
