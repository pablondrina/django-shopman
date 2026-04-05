"""
Device management views.

GET /auth/devices/       — List trusted devices for authenticated customer
DELETE /auth/devices/<id>/ — Revoke a specific device
DELETE /auth/devices/    — Revoke all devices (clears cookie too)
"""

from __future__ import annotations

import logging
import uuid

from django.http import JsonResponse
from django.views import View

from ..conf import auth_settings
from ..models.device_trust import TrustedDevice
from ..services.device_trust import DeviceTrustService

logger = logging.getLogger("shopman.auth.views.devices")


def _get_customer_id(request) -> uuid.UUID | None:
    """Extract customer_id from authenticated request."""
    customer_info = getattr(request, "customer", None)
    if customer_info is not None:
        return customer_info.uuid
    return None


class DeviceListView(View):
    """List and revoke-all trusted devices for the authenticated customer."""

    def get(self, request):
        customer_id = _get_customer_id(request)
        if customer_id is None:
            return JsonResponse({"error": "Authentication required."}, status=401)

        devices = TrustedDevice.objects.filter(
            customer_id=customer_id,
            is_active=True,
        ).order_by("-last_used_at", "-created_at")

        data = [
            {
                "id": str(d.id),
                "label": d.label,
                "created_at": d.created_at.isoformat(),
                "last_used_at": d.last_used_at.isoformat() if d.last_used_at else None,
                "is_current": _is_current_device(request, d),
            }
            for d in devices
            if d.is_valid
        ]

        return JsonResponse({"devices": data})

    def delete(self, request):
        """Revoke ALL trusted devices for the customer."""
        customer_id = _get_customer_id(request)
        if customer_id is None:
            return JsonResponse({"error": "Authentication required."}, status=401)

        count = DeviceTrustService.revoke_all(customer_id)

        # Clear device trust cookie on response
        response = JsonResponse({"revoked": count})
        cookie_name = auth_settings.DEVICE_TRUST_COOKIE_NAME
        response.delete_cookie(cookie_name)

        logger.info(
            "All devices revoked via management endpoint",
            extra={"customer_id": str(customer_id), "count": count},
        )

        return response


class DeviceRevokeView(View):
    """Revoke a specific trusted device by ID."""

    def delete(self, request, device_id):
        customer_id = _get_customer_id(request)
        if customer_id is None:
            return JsonResponse({"error": "Authentication required."}, status=401)

        try:
            device_uuid = uuid.UUID(str(device_id))
        except ValueError:
            return JsonResponse({"error": "Invalid device ID."}, status=400)

        try:
            device = TrustedDevice.objects.get(
                id=device_uuid,
                customer_id=customer_id,
                is_active=True,
            )
        except TrustedDevice.DoesNotExist:
            return JsonResponse({"error": "Device not found."}, status=404)

        device.revoke()

        response = JsonResponse({"revoked": True, "id": str(device.id)})

        # If revoking the current device, clear cookie
        if _is_current_device(request, device):
            cookie_name = auth_settings.DEVICE_TRUST_COOKIE_NAME
            response.delete_cookie(cookie_name)

        logger.info(
            "Device revoked via management endpoint",
            extra={
                "customer_id": str(customer_id),
                "device_id": str(device.id),
            },
        )

        return response


def _is_current_device(request, device: TrustedDevice) -> bool:
    """Check if a device matches the current request's cookie."""
    from ..conf import auth_settings

    raw_token = request.COOKIES.get(auth_settings.DEVICE_TRUST_COOKIE_NAME)
    if not raw_token:
        return False
    from ..models.device_trust import _hash_token

    return device.token_hash == _hash_token(raw_token)
