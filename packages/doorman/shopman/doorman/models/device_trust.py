"""
TrustedDevice model — Device trust for skip-OTP on repeat logins.

When a user successfully verifies via OTP, we can mark their device as trusted.
On subsequent logins from the same device, we skip the full OTP flow.

Security:
- Device identified by a secure random token stored in a HttpOnly cookie.
- Token stored as HMAC digest in DB (never plaintext).
- TTL-based expiration (default 30 days).
- Can be revoked per-customer or globally.
"""

import hashlib
import hmac
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _get_hmac_key() -> bytes:
    """Get the HMAC key for device token hashing."""
    return settings.SECRET_KEY.encode("utf-8")


def _hash_token(raw_token: str) -> str:
    """Compute HMAC-SHA256 hex digest for a device token."""
    return hmac.new(
        _get_hmac_key(), raw_token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _default_expires_at():
    from ..conf import doorman_settings

    return timezone.now() + timedelta(days=doorman_settings.DEVICE_TRUST_TTL_DAYS)


class TrustedDevice(models.Model):
    """
    A trusted device for a customer.

    After OTP verification, a secure cookie is set on the device.
    On next login from this device, the customer can skip OTP.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Link to customer (UUID, not FK — same decoupling pattern)
    customer_id = models.UUIDField(
        _("ID do cliente"),
        db_index=True,
        help_text=_("UUID do cliente no Guestman"),
    )

    # Device identification (HMAC of the cookie token)
    token_hash = models.CharField(
        _("hash do token"),
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("HMAC-SHA256 do token do cookie."),
    )

    # Device metadata
    user_agent = models.CharField(
        _("user agent"), max_length=512, blank=True, default=""
    )
    ip_address = models.GenericIPAddressField(
        _("endereço IP"), null=True, blank=True
    )
    label = models.CharField(
        _("rótulo"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("Ex: 'Chrome no iPhone', derivado do user-agent."),
    )

    # Lifecycle
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expira em"), default=_default_expires_at)
    last_used_at = models.DateTimeField(_("último uso"), null=True, blank=True)
    is_active = models.BooleanField(_("ativo"), default=True)

    class Meta:
        db_table = "shopman_auth_trusted_device"
        verbose_name = _("dispositivo confiável")
        verbose_name_plural = _("dispositivos confiáveis")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer_id", "is_active"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        status = "active" if self.is_valid else "expired"
        return f"Device {self.token_hash[:8]}… for customer {self.customer_id} ({status})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        return self.is_active and not self.is_expired

    def touch(self):
        """Update last_used_at timestamp."""
        self.last_used_at = timezone.now()
        self.save(update_fields=["last_used_at"])

    def revoke(self):
        """Revoke this trusted device."""
        self.is_active = False
        self.save(update_fields=["is_active"])

    # ===========================================
    # Class methods
    # ===========================================

    @classmethod
    def create_for_customer(
        cls,
        customer_id: uuid.UUID,
        user_agent: str = "",
        ip_address: str | None = None,
        label: str = "",
    ) -> tuple["TrustedDevice", str]:
        """
        Create a trusted device and return (device, raw_token).

        The raw_token should be stored in a secure HttpOnly cookie.
        The DB only stores the HMAC digest.
        """
        raw_token = secrets.token_urlsafe(32)
        device = cls.objects.create(
            customer_id=customer_id,
            token_hash=_hash_token(raw_token),
            user_agent=user_agent[:512],
            ip_address=ip_address,
            label=label or _derive_label(user_agent),
        )
        return device, raw_token

    @classmethod
    def verify_token(cls, raw_token: str) -> "TrustedDevice | None":
        """
        Verify a raw device token against stored hashes.

        Returns the TrustedDevice if valid, None otherwise.
        Uses HMAC comparison for timing-safety.
        """
        token_hash = _hash_token(raw_token)
        try:
            device = cls.objects.get(token_hash=token_hash)
        except cls.DoesNotExist:
            return None

        if not device.is_valid:
            return None

        device.touch()
        return device

    @classmethod
    def revoke_all_for_customer(cls, customer_id: uuid.UUID) -> int:
        """Revoke all trusted devices for a customer."""
        return cls.objects.filter(
            customer_id=customer_id, is_active=True
        ).update(is_active=False)

    @classmethod
    def cleanup_expired(cls, days: int = 7) -> int:
        """Delete expired devices older than N days."""
        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = cls.objects.filter(expires_at__lt=cutoff).delete()
        return deleted


def _derive_label(user_agent: str) -> str:
    """Derive a human-readable label from user-agent string."""
    if not user_agent:
        return ""
    ua = user_agent.lower()
    parts = []
    if "chrome" in ua and "edg" not in ua:
        parts.append("Chrome")
    elif "firefox" in ua:
        parts.append("Firefox")
    elif "safari" in ua and "chrome" not in ua:
        parts.append("Safari")
    elif "edg" in ua:
        parts.append("Edge")

    if "iphone" in ua:
        parts.append("iPhone")
    elif "android" in ua:
        parts.append("Android")
    elif "macintosh" in ua or "mac os" in ua:
        parts.append("Mac")
    elif "windows" in ua:
        parts.append("Windows")
    elif "linux" in ua:
        parts.append("Linux")

    return " / ".join(parts) if parts else ""
