"""
DeviceTrustService — Manage device trust for skip-OTP logins.

After OTP verification, a user can trust their device via a secure
HttpOnly cookie. On subsequent visits, the device token is checked
and if valid, the user can login without OTP.

Security:
- Cookie is HttpOnly, Secure (in production), SameSite=Lax.
- Token in DB stored as HMAC digest (never plaintext).
- TTL-based expiration.
- Can be revoked per-customer.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from ..conf import gating_settings
from ..models.device_trust import TrustedDevice
from ..signals import device_trusted

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("shopman.gating.device_trust")

# Cookie name for device trust token
COOKIE_NAME_ATTR = "DEVICE_TRUST_COOKIE_NAME"


class DeviceTrustService:
    """Service for device trust operations."""

    @classmethod
    def check_device_trust(
        cls, request: HttpRequest, customer_id: uuid.UUID
    ) -> bool:
        """
        Check if the current request comes from a trusted device
        for the given customer.

        Returns True if the device is trusted and the customer matches.
        """
        if not gating_settings.DEVICE_TRUST_ENABLED:
            return False

        cookie_name = gating_settings.DEVICE_TRUST_COOKIE_NAME
        raw_token = request.COOKIES.get(cookie_name)
        if not raw_token:
            return False

        device = TrustedDevice.verify_token(raw_token)
        if device is None:
            return False

        # Ensure the device belongs to this customer
        if device.customer_id != customer_id:
            return False

        logger.info(
            "Device trust verified",
            extra={
                "customer_id": str(customer_id),
                "device_id": str(device.id),
            },
        )
        return True

    @classmethod
    def trust_device(
        cls,
        response: HttpResponse,
        customer_id: uuid.UUID,
        request: HttpRequest,
    ) -> TrustedDevice | None:
        """
        Create a trusted device and set the cookie on the response.

        Call this after successful OTP verification.

        Returns the TrustedDevice or None if device trust is disabled.
        """
        if not gating_settings.DEVICE_TRUST_ENABLED:
            return None

        user_agent = request.META.get("HTTP_USER_AGENT", "")
        from ..utils import get_client_ip

        ip = get_client_ip(request, gating_settings.TRUSTED_PROXY_DEPTH)

        device, raw_token = TrustedDevice.create_for_customer(
            customer_id=customer_id,
            user_agent=user_agent,
            ip_address=ip,
        )

        # Set cookie
        cookie_name = gating_settings.DEVICE_TRUST_COOKIE_NAME
        max_age = gating_settings.DEVICE_TRUST_TTL_DAYS * 86400
        response.set_cookie(
            cookie_name,
            raw_token,
            max_age=max_age,
            httponly=True,
            secure=gating_settings.USE_HTTPS,
            samesite="Lax",
        )

        # Signal
        device_trusted.send(
            sender=cls,
            device=device,
            customer_id=customer_id,
            request=request,
        )

        logger.info(
            "Device trusted",
            extra={
                "customer_id": str(customer_id),
                "device_id": str(device.id),
                "label": device.label,
            },
        )

        return device

    @classmethod
    def revoke_device(cls, request: HttpRequest, response: HttpResponse) -> None:
        """Revoke the trusted device from the current request and clear cookie."""
        cookie_name = gating_settings.DEVICE_TRUST_COOKIE_NAME
        raw_token = request.COOKIES.get(cookie_name)
        if raw_token:
            device = TrustedDevice.verify_token(raw_token)
            if device:
                device.revoke()
                logger.info(
                    "Device trust revoked",
                    extra={"device_id": str(device.id)},
                )
        response.delete_cookie(cookie_name)

    @classmethod
    def revoke_all(cls, customer_id: uuid.UUID) -> int:
        """Revoke all trusted devices for a customer."""
        count = TrustedDevice.revoke_all_for_customer(customer_id)
        if count:
            logger.info(
                "All devices revoked",
                extra={"customer_id": str(customer_id), "count": count},
            )
        return count

    @classmethod
    def cleanup(cls, days: int = 7) -> int:
        """Delete expired device trust records older than N days."""
        return TrustedDevice.cleanup_expired(days)
