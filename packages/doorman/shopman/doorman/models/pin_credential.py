"""
PinCredential model — a short-secret credential bound to a principal (User).

Generic auth primitive: a persistent PIN (numeric short secret) verified against
an HMAC digest, with attempt counting and lockout. NOT tied to any vertical
(POS, KDS, admin step-up, kiosk… any surface that needs fast principal
re-identification can use it). Sibling of :class:`VerificationCode` (OTP): OTP is
one-time and channel-delivered; a PIN is persistent and principal-set.

Security and policy are parameters (DOORMAN settings), never baked in. Only the
HMAC digest is stored — never the plaintext PIN.
"""

import hashlib
import hmac
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def _pin_hmac_key() -> bytes:
    """HMAC key for PIN hashing (falls back to SECRET_KEY)."""
    from ..conf import doorman_settings

    key = getattr(doorman_settings, "PIN_HMAC_KEY", "") or settings.SECRET_KEY
    return key.encode("utf-8")


def hash_pin(raw_pin: str) -> str:
    """Compute the HMAC-SHA256 hex digest of a raw PIN."""
    return hmac.new(_pin_hmac_key(), raw_pin.strip().encode("utf-8"), hashlib.sha256).hexdigest()


def hash_badge(raw_token: str) -> str:
    """HMAC-SHA256 hex digest of a raw badge token (the barcode value).

    The badge is an alternative, possession-based identifier for the same
    principal — a long random token printed as a barcode on the operator's badge,
    scanned in place of typing the PIN. Only the digest is stored, never the token.
    """
    return hmac.new(_pin_hmac_key(), (raw_token or "").strip().encode("utf-8"), hashlib.sha256).hexdigest()


def pin_matches(stored_digest: str, raw_pin: str) -> bool:
    """Constant-time compare a raw PIN against a stored digest.

    Pure cryptographic primitive — does NOT check lockout/attempts. Callers that
    need full lifecycle validation must use :meth:`PinCredential.verify`.
    """
    return hmac.compare_digest(stored_digest, hash_pin(raw_pin))


def _default_max_attempts() -> int:
    from ..conf import doorman_settings

    return doorman_settings.PIN_MAX_ATTEMPTS


class PinCredentialError(ValueError):
    """Raised when a PIN does not satisfy the configured policy."""


class PinCredential(models.Model):
    """A PIN credential for a principal (Django User).

    One active PIN per user. Rotating the PIN overwrites the digest and resets
    the lockout state.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="pin_credential",
        verbose_name=_("principal"),
    )
    pin_hash = models.CharField(
        _("hash do PIN"),
        max_length=64,
        help_text=_("HMAC-SHA256 do PIN. Nunca armazena plaintext."),
    )
    badge_hash = models.CharField(
        _("hash do crachá"),
        max_length=64,
        null=True,
        blank=True,
        default=None,
        unique=True,
        db_index=True,
        help_text=_("HMAC-SHA256 do token do crachá (código de barras). Alternativa ao PIN. Nunca armazena plaintext."),
    )

    # Security / lockout
    attempts = models.PositiveSmallIntegerField(_("tentativas falhas"), default=0)
    max_attempts = models.PositiveSmallIntegerField(_("máximo de tentativas"), default=_default_max_attempts)
    locked_until = models.DateTimeField(_("bloqueado até"), null=True, blank=True)
    # Provisionado/resetado pelo gerente com PIN temporário → força a troca no 1º uso.
    must_change = models.BooleanField(_("trocar no próximo uso"), default=False)

    # Lifecycle
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)
    last_verified_at = models.DateTimeField(_("última verificação"), null=True, blank=True)

    class Meta:
        db_table = "doorman_pin_credential"
        verbose_name = _("credencial PIN")
        verbose_name_plural = _("credenciais PIN")
        ordering = ["-updated_at"]

    def __str__(self):
        return f"PIN de {self.user} ({'bloqueado' if self.is_locked else 'ativo'})"

    @property
    def is_locked(self) -> bool:
        """Whether the credential is currently locked out."""
        return self.locked_until is not None and timezone.now() < self.locked_until

    @property
    def attempts_remaining(self) -> int:
        return max(0, self.max_attempts - self.attempts)

    @staticmethod
    def validate_raw(raw_pin: str) -> str:
        """Validate a raw PIN against the configured policy. Returns the cleaned PIN."""
        from ..conf import doorman_settings

        pin = (raw_pin or "").strip()
        if len(pin) < doorman_settings.PIN_MIN_LENGTH:
            raise PinCredentialError(
                f"PIN deve ter pelo menos {doorman_settings.PIN_MIN_LENGTH} dígitos"
            )
        if doorman_settings.PIN_DIGITS_ONLY and not pin.isdigit():
            raise PinCredentialError("PIN deve conter apenas dígitos")
        return pin

    def set_pin(self, raw_pin: str, *, must_change: bool = False) -> None:
        """Set/rotate the PIN. Valida policy, reseta lockout e o flag must_change.

        Uma troca real (must_change=False, o default) remove a exigência de troca;
        um reset do gerente passa must_change=True para forçar a troca no 1º uso.
        """
        pin = self.validate_raw(raw_pin)
        self.pin_hash = hash_pin(pin)
        self.attempts = 0
        self.locked_until = None
        self.must_change = must_change
        if self.pk:
            self.save(update_fields=["pin_hash", "attempts", "locked_until", "must_change", "updated_at"])

    def verify(self, raw_pin: str) -> bool:
        """Verify a raw PIN. Honors lockout; records failures; clears on success.

        Returns True only if not locked and the digest matches.
        """
        if self.is_locked:
            return False
        if pin_matches(self.pin_hash, raw_pin):
            self.attempts = 0
            self.locked_until = None
            self.last_verified_at = timezone.now()
            self.save(update_fields=["attempts", "locked_until", "last_verified_at"])
            return True
        self._record_failure()
        return False

    def _record_failure(self) -> None:
        """Record a failed attempt; lock out when the limit is reached."""
        from datetime import timedelta

        from django.db.models import F

        from ..conf import doorman_settings

        PinCredential.objects.filter(pk=self.pk).update(attempts=F("attempts") + 1)
        self.refresh_from_db(fields=["attempts"])
        if self.attempts >= self.max_attempts:
            self.locked_until = timezone.now() + timedelta(minutes=doorman_settings.PIN_LOCKOUT_MINUTES)
            self.save(update_fields=["locked_until"])

    def unlock(self) -> None:
        """Clear the lockout and reset attempts (e.g. manager override)."""
        self.attempts = 0
        self.locked_until = None
        self.save(update_fields=["attempts", "locked_until"])

    @classmethod
    def set_for(cls, user, raw_pin: str, *, must_change: bool = False) -> "PinCredential":
        """Create or rotate the PIN for a user (must_change força troca no 1º uso)."""
        cred, _created = cls.objects.get_or_create(user=user, defaults={"pin_hash": ""})
        cred.set_pin(raw_pin, must_change=must_change)
        return cred

    # ── Badge (barcode) — possession-based alternative to the PIN ────────────

    def set_badge(self, raw_token: str) -> None:
        """Store the digest of a badge token (already-minted barcode value)."""
        self.badge_hash = hash_badge(raw_token)
        if self.pk:
            self.save(update_fields=["badge_hash", "updated_at"])

    def clear_badge(self) -> None:
        """Revoke the badge (e.g. lost crachá)."""
        self.badge_hash = None
        if self.pk:
            self.save(update_fields=["badge_hash", "updated_at"])

    @classmethod
    def issue_badge(cls, user) -> str:
        """Mint a fresh random badge token, store its digest, return the raw token.

        The caller encodes the returned value as a Code-128 barcode on the badge.
        24 hex chars (96 bits) — unguessable, and comfortably inside a barcode.
        """
        import secrets

        cred, _created = cls.objects.get_or_create(user=user, defaults={"pin_hash": ""})
        raw = secrets.token_hex(12)
        cred.set_badge(raw)
        return raw

    @classmethod
    def resolve_by_badge(cls, raw_token: str):
        """Return the principal (User) whose badge matches, or None.

        Possession-based: a 96-bit token is not brute-forceable, so this is not
        coupled to the PIN lockout. Eligibility (active/staff/perm) is enforced by
        the caller (operator service), not here.
        """
        token = (raw_token or "").strip()
        if not token:
            return None
        try:
            cred = cls.objects.select_related("user").get(badge_hash=hash_badge(token))
        except cls.DoesNotExist:
            return None
        return cred.user
