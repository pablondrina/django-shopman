"""
MagicCode model - OTP code for verification.
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
    """Get the HMAC key for OTP hashing."""
    from ..conf import gating_settings
    key = getattr(gating_settings, "OTP_HMAC_KEY", "") or settings.SECRET_KEY
    return key.encode("utf-8")


def generate_code() -> str:
    """Generate a 6-digit code and return its HMAC digest."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    return _hmac_code(code)


def generate_raw_code() -> tuple[str, str]:
    """Generate a 6-digit code. Returns (raw_code, hmac_digest)."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    return code, _hmac_code(code)


def _hmac_code(code: str) -> str:
    """Compute HMAC-SHA256 hex digest for a code."""
    return hmac.new(_get_hmac_key(), code.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_code(stored_digest: str, code_input: str) -> bool:
    """Verify a code against its stored HMAC digest."""
    input_digest = _hmac_code(code_input.strip())
    return hmac.compare_digest(stored_digest, input_digest)


def default_code_expiry():
    """Default expiration time for magic codes."""
    from ..conf import gating_settings

    return timezone.now() + timedelta(minutes=gating_settings.MAGIC_CODE_TTL_MINUTES)


def _default_max_attempts():
    from shopman.gating.conf import gating_settings
    return gating_settings.MAGIC_CODE_MAX_ATTEMPTS


class MagicCode(models.Model):
    """
    OTP code for verification.

    Flows:
    - LOGIN: Customer provides phone -> code -> session
    - VERIFY_CONTACT: Customer adds contact -> code -> verified
    """

    class DeliveryMethod(models.TextChoices):
        WHATSAPP = "whatsapp", _("WhatsApp")
        SMS = "sms", _("SMS")
        EMAIL = "email", _("Email")

    class Status(models.TextChoices):
        PENDING = "pending", _("Pendente")
        SENT = "sent", _("Enviado")
        VERIFIED = "verified", _("Verificado")
        EXPIRED = "expired", _("Expirado")
        FAILED = "failed", _("Falhou")

    class Purpose(models.TextChoices):
        LOGIN = "login", _("Login")
        VERIFY_CONTACT = "verify_contact", _("Verificar Contato")

    # Identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code_hash = models.CharField(
        _("hash do código"),
        max_length=64,
        default=generate_code,
        help_text=_("HMAC-SHA256 do código OTP. Nunca armazena plaintext."),
    )

    # Target
    target_value = models.CharField(
        _("valor destino"),
        max_length=255,
        db_index=True,
        help_text=_("Telefone em E.164 ou email."),
    )

    # Purpose
    purpose = models.CharField(
        _("finalidade"),
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.LOGIN,
    )

    # Lifecycle
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expira em"), default=default_code_expiry)
    sent_at = models.DateTimeField(_("enviado em"), null=True, blank=True)
    verified_at = models.DateTimeField(_("verificado em"), null=True, blank=True)

    # Delivery
    delivery_method = models.CharField(
        _("método de envio"),
        max_length=20,
        choices=DeliveryMethod.choices,
        default=DeliveryMethod.WHATSAPP,
    )

    # Security
    attempts = models.PositiveSmallIntegerField(_("tentativas"), default=0)
    max_attempts = models.PositiveSmallIntegerField(_("máximo de tentativas"), default=_default_max_attempts)
    ip_address = models.GenericIPAddressField(_("endereço IP"), null=True, blank=True)

    # Result (Customer UUID from Guestman)
    customer_id = models.UUIDField(
        _("ID do cliente"),
        null=True,
        blank=True,
        help_text=_("UUID do cliente no Guestman"),
    )

    class Meta:
        db_table = "gating_magic_code"
        verbose_name = _("código de verificação")
        verbose_name_plural = _("códigos de verificação")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_value", "status", "created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        return f"Code {self.code_hash[:12]}… for {self.target_value} ({self.status})"

    @property
    def is_expired(self) -> bool:
        """Check if code is expired."""
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if code is valid for verification."""
        return (
            self.status in [self.Status.PENDING, self.Status.SENT]
            and not self.is_expired
            and self.attempts < self.max_attempts
        )

    @property
    def attempts_remaining(self) -> int:
        """Number of attempts remaining."""
        return max(0, self.max_attempts - self.attempts)

    def record_attempt(self):
        """Record a failed verification attempt (atomic increment)."""
        from django.db.models import F

        MagicCode.objects.filter(pk=self.pk).update(attempts=F("attempts") + 1)
        self.refresh_from_db(fields=["attempts"])
        if self.attempts >= self.max_attempts:
            self.status = self.Status.FAILED
            self.save(update_fields=["status"])

    def mark_sent(self):
        """Mark code as sent."""
        self.status = self.Status.SENT
        self.sent_at = timezone.now()
        self.save(update_fields=["status", "sent_at"])

    def mark_verified(self, customer_id):
        """Mark code as verified."""
        self.status = self.Status.VERIFIED
        self.verified_at = timezone.now()
        self.customer_id = customer_id
        self.save(update_fields=["status", "verified_at", "customer_id"])

    def mark_expired(self):
        """Mark code as expired."""
        self.status = self.Status.EXPIRED
        self.save(update_fields=["status"])
