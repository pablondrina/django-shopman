"""
AccessLink model - Token for creating web session from chat or email.

Security:
- Token stored as HMAC-SHA256 digest in DB (never plaintext).
- Raw token is returned only at creation time for delivery to customer.
- Lookup uses hash comparison (same pattern as TrustedDevice).
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
    """Get the HMAC key for access link token hashing."""
    return settings.SECRET_KEY.encode("utf-8")


def generate_token() -> str:
    """Legacy: kept for migration compatibility. Not used in new code."""
    return secrets.token_urlsafe(32)


def _hash_token(raw_token: str) -> str:
    """Compute HMAC-SHA256 hex digest for an access link token."""
    return hmac.new(
        _get_hmac_key(), raw_token.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def default_expiry():
    """Default expiration time for access links."""
    from ..conf import doorman_settings

    return timezone.now() + timedelta(minutes=doorman_settings.ACCESS_LINK_EXCHANGE_TTL_MINUTES)


class AccessLink(models.Model):
    """
    Token for creating web session from chat or email.

    Flow:
    1. Manychat/backend calls POST /auth/access/create/
    2. Receives URL with token
    3. Sends to customer
    4. Customer clicks -> GET /auth/access/?t=...
    5. Auth validates, creates session, redirects

    Security:
    - Single-use
    - Short TTL (5 min default)
    - Audience limits scope
    """

    class Audience(models.TextChoices):
        WEB_CHECKOUT = "web_checkout", _("Checkout")
        WEB_ACCOUNT = "web_account", _("Conta")
        WEB_SUPPORT = "web_support", _("Suporte")
        WEB_GENERAL = "web_general", _("Geral")

    class Source(models.TextChoices):
        MANYCHAT = "manychat", _("ManyChat")
        INTERNAL = "internal", _("Interno")
        API = "api", _("API")

    # Identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    token_hash = models.CharField(
        _("hash do token"),
        max_length=64,
        unique=True,
        db_index=True,
        help_text=_("HMAC-SHA256 do token. Token bruto nunca é persistido."),
    )

    # Target (Customer UUID from Guestman)
    customer_id = models.UUIDField(
        _("ID do cliente"),
        db_index=True,
        help_text=_("UUID do cliente no Guestman"),
    )

    # Scope
    audience = models.CharField(
        _("audiência"),
        max_length=20,
        choices=Audience.choices,
        default=Audience.WEB_GENERAL,
        help_text=_("Escopo do token"),
    )

    # Lifecycle
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    expires_at = models.DateTimeField(_("expira em"), default=default_expiry)
    used_at = models.DateTimeField(_("usado em"), null=True, blank=True)

    # Context
    source = models.CharField(
        _("origem"),
        max_length=20,
        choices=Source.choices,
        default=Source.MANYCHAT,
    )
    metadata = models.JSONField(
        _("metadados"), default=dict, blank=True,
        help_text=_('Metadados do token. Ex: {"device": "iPhone 15", "login_source": "whatsapp"}'),
    )

    # Result
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="doorman_access_links",
        verbose_name=_("usuário"),
    )

    class Meta:
        db_table = "doorman_access_link"
        verbose_name = _("link de acesso")
        verbose_name_plural = _("links de acesso")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer_id", "created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        status = "used" if self.used_at else ("expired" if self.is_expired else "valid")
        return f"AccessLink {self.token_hash[:8]}… ({status})"

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return timezone.now() > self.expires_at

    @property
    def is_valid(self) -> bool:
        """Check if token is valid for use."""
        return not self.used_at and not self.is_expired

    def mark_used(self, user):
        """Mark token as used."""
        self.used_at = timezone.now()
        self.user = user
        self.save(update_fields=["used_at", "user"])

    def get_customer(self):
        """Fetch customer info via resolver."""
        from ..conf import get_customer_resolver

        resolver = get_customer_resolver()
        return resolver.get_by_uuid(self.customer_id)

    # ===========================================
    # Class methods for secure token handling
    # ===========================================

    @classmethod
    def create_with_token(
        cls,
        customer_id: uuid.UUID,
        audience: str = "web_general",
        source: str = "manychat",
        expires_at=None,
        metadata: dict | None = None,
    ) -> tuple["AccessLink", str]:
        """
        Create an AccessLink and return (link, raw_token).

        The raw_token is returned only once for delivery to the customer.
        The DB stores only the HMAC-SHA256 digest.
        """
        raw_token = secrets.token_urlsafe(32)
        kwargs = {
            "customer_id": customer_id,
            "token_hash": _hash_token(raw_token),
            "audience": audience,
            "source": source,
            "metadata": metadata or {},
        }
        if expires_at is not None:
            kwargs["expires_at"] = expires_at
        link = cls.objects.create(**kwargs)
        return link, raw_token

    @classmethod
    def get_by_token(cls, raw_token: str, *, for_update: bool = False) -> "AccessLink | None":
        """
        Look up an AccessLink by raw token.

        Computes HMAC and queries by hash — never stores or queries plaintext.
        """
        token_hash = _hash_token(raw_token)
        queryset = cls.objects
        if for_update:
            queryset = queryset.select_for_update()
        try:
            return queryset.get(token_hash=token_hash)
        except cls.DoesNotExist:
            return None
