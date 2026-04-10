"""
AccessLink model - Token for creating web session from chat or email.
"""

import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


def generate_token() -> str:
    """Generate a secure URL-safe token."""
    return secrets.token_urlsafe(32)


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
    token = models.CharField(
        _("token"),
        max_length=64,
        unique=True,
        db_index=True,
        default=generate_token,
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
        related_name="shopman_auth_access_links",
        verbose_name=_("usuário"),
    )

    class Meta:
        db_table = "shopman_auth_access_link"
        verbose_name = _("link de acesso")
        verbose_name_plural = _("links de acesso")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["customer_id", "created_at"]),
            models.Index(fields=["expires_at"]),
        ]

    def __str__(self):
        status = "used" if self.used_at else ("expired" if self.is_expired else "valid")
        return f"AccessLink {self.token[:8]}... ({status})"

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
