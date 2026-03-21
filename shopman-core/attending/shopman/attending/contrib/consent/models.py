"""CommunicationConsent model — LGPD/GDPR opt-in/opt-out per channel."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class ConsentChannel(models.TextChoices):
    """Communication channels requiring consent."""

    WHATSAPP = "whatsapp", _("WhatsApp")
    EMAIL = "email", _("Email")
    SMS = "sms", _("SMS")
    PUSH = "push", _("Push Notification")


class ConsentStatus(models.TextChoices):
    """Consent states."""

    OPTED_IN = "opted_in", _("Opt-in")
    OPTED_OUT = "opted_out", _("Opt-out")
    PENDING = "pending", _("Pendente")


class LegalBasis(models.TextChoices):
    """LGPD legal basis for data processing."""

    CONSENT = "consent", _("Consentimento")
    LEGITIMATE_INTEREST = "legitimate_interest", _("Interesse legítimo")
    CONTRACT = "contract", _("Execução de contrato")
    LEGAL_OBLIGATION = "legal_obligation", _("Obrigação legal")


class CommunicationConsent(models.Model):
    """
    Per-channel communication consent for a customer.

    LGPD requires explicit, informed, and revocable consent for
    marketing communications. This model tracks:
    - Which channels the customer opted into/out of
    - When consent was granted or revoked
    - The source (how consent was collected)
    - Legal basis for processing

    Rules:
    - One record per (customer, channel)
    - Default status is 'pending' (no communication until opted_in)
    - Revocation is immediate and logged
    - Audit trail preserved (consented_at, revoked_at)
    """

    customer = models.ForeignKey(
        "attending.Customer",
        on_delete=models.CASCADE,
        related_name="consents",
        verbose_name=_("cliente"),
    )

    channel = models.CharField(
        _("canal"),
        max_length=20,
        choices=ConsentChannel.choices,
        db_index=True,
    )
    status = models.CharField(
        _("status"),
        max_length=20,
        choices=ConsentStatus.choices,
        default=ConsentStatus.PENDING,
    )

    # Legal
    legal_basis = models.CharField(
        _("base legal"),
        max_length=30,
        choices=LegalBasis.choices,
        default=LegalBasis.CONSENT,
        help_text=_("Base legal LGPD para o tratamento de dados"),
    )

    # Source
    source = models.CharField(
        _("origem"),
        max_length=100,
        blank=True,
        help_text=_("Como o consentimento foi coletado (checkout, form, whatsapp)"),
    )
    ip_address = models.GenericIPAddressField(
        _("endereço IP"),
        blank=True,
        null=True,
        help_text=_("IP no momento do consentimento"),
    )

    # Timestamps
    consented_at = models.DateTimeField(
        _("consentido em"),
        null=True,
        blank=True,
        help_text=_("Data/hora do opt-in"),
    )
    revoked_at = models.DateTimeField(
        _("revogado em"),
        null=True,
        blank=True,
        help_text=_("Data/hora do opt-out"),
    )

    # Audit
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("consentimento de comunicação")
        verbose_name_plural = _("consentimentos de comunicação")
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "channel"],
                name="guestman_unique_consent_per_channel",
            ),
        ]
        ordering = ["channel"]

    def __str__(self):
        return f"{self.customer.ref}: {self.channel} → {self.status}"

    @property
    def is_active(self) -> bool:
        """Whether communication is allowed on this channel."""
        return self.status == ConsentStatus.OPTED_IN
