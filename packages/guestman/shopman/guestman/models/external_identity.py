"""
ExternalIdentity model - Link to external providers.
"""

import uuid

from django.db import models
from django.utils.translation import gettext_lazy as _


class ExternalIdentity(models.Model):
    """
    Customer link to external provider.

    Providers:
    - MANYCHAT: Manychat subscriber
    - WHATSAPP: WhatsApp Business API
    - INSTAGRAM: Instagram account
    - GOOGLE: Google OAuth (via Auth)
    - APPLE: Apple Sign In (via Auth)

    Rules:
    - (provider, provider_uid) is globally unique
    """

    class Provider(models.TextChoices):
        MANYCHAT = "manychat", _("ManyChat")
        WHATSAPP = "whatsapp", _("WhatsApp Business")
        INSTAGRAM = "instagram", _("Instagram")
        FACEBOOK = "facebook", _("Facebook")
        GOOGLE = "google", _("Google")
        APPLE = "apple", _("Apple")
        TELEGRAM = "telegram", _("Telegram")
        OTHER = "other", _("Outro")

    # Identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        "guestman.Customer",
        on_delete=models.CASCADE,
        related_name="external_identities",
        verbose_name=_("cliente"),
    )

    # Provider data
    provider = models.CharField(
        _("provedor"),
        max_length=20,
        choices=Provider.choices,
    )
    provider_uid = models.CharField(
        _("ID no provedor"),
        max_length=255,
        help_text=_("ID único no provedor (ex: Manychat subscriber_id)"),
    )
    provider_meta = models.JSONField(
        _("metadados do provedor"),
        default=dict,
        blank=True,
        help_text=_('Dados do provedor externo. Ex: {"wa_id": "5543...", "ig_scoped_id": "abc123"}'),
    )

    # Status
    is_active = models.BooleanField(_("ativo"), default=True)

    # Timestamps
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        db_table = "customers_external_identity"
        verbose_name = _("identidade externa")
        verbose_name_plural = _("identidades externas")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_uid"],
                name="customers_unique_external_identity",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "provider"]),
            models.Index(fields=["provider", "provider_uid"]),
        ]

    def __str__(self):
        status = "V" if self.is_active else "o"
        uid_short = (
            self.provider_uid[:20] + "..." if len(self.provider_uid) > 20 else self.provider_uid
        )
        return f"{status} {self.provider}: {uid_short}"
