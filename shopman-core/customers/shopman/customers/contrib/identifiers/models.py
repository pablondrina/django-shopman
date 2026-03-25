"""CustomerIdentifier model for multi-channel deduplication."""

import re

from django.db import models
from django.utils.translation import gettext_lazy as _


class IdentifierType(models.TextChoices):
    """Supported identifier types."""

    PHONE = "phone", _("Telefone")
    EMAIL = "email", _("Email")
    INSTAGRAM = "instagram", _("Instagram")
    FACEBOOK = "facebook", _("Facebook")
    WHATSAPP = "whatsapp", _("WhatsApp")
    TELEGRAM = "telegram", _("Telegram")
    MANYCHAT = "manychat", _("Manychat ID")
    CPF = "cpf", _("CPF")
    IFOOD = "ifood", _("iFood")


class CustomerIdentifier(models.Model):
    """
    Unique customer identifier.

    Allows:
    - Finding customer by any channel
    - Detecting duplicates across channels
    - Maintaining identifier history
    """

    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="identifiers",
        verbose_name=_("cliente"),
    )
    identifier_type = models.CharField(
        _("tipo"),
        max_length=20,
        choices=IdentifierType.choices,
    )
    identifier_value = models.CharField(
        _("valor"),
        max_length=255,
        help_text=_("Valor normalizado (telefone sem formatação, email minúsculo)"),
    )
    is_primary = models.BooleanField(
        _("principal"),
        default=False,
        help_text=_("Identificador principal deste tipo"),
    )
    verified_at = models.DateTimeField(
        _("verificado em"),
        null=True,
        blank=True,
        help_text=_("Quando foi verificado (ex: OTP)"),
    )

    # Audit
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    source_system = models.CharField(_("sistema de origem"), max_length=100, blank=True)

    class Meta:
        verbose_name = _("identificador")
        verbose_name_plural = _("identificadores")
        constraints = [
            models.UniqueConstraint(
                fields=["identifier_type", "identifier_value"],
                name="customers_unique_identifier",
            ),
        ]
        indexes = [
            models.Index(fields=["identifier_type", "identifier_value"]),
        ]

    def __str__(self):
        return f"{self.get_identifier_type_display()}: {self.identifier_value}"

    def save(self, *args, **kwargs):
        # Normalize value using centralized function
        from shopman.customers.utils import normalize_phone

        if self.identifier_type in (IdentifierType.PHONE, IdentifierType.WHATSAPP):
            self.identifier_value = normalize_phone(self.identifier_value)
        elif self.identifier_type == IdentifierType.EMAIL:
            self.identifier_value = self.identifier_value.lower().strip()
        elif self.identifier_type == IdentifierType.INSTAGRAM:
            self.identifier_value = normalize_phone(
                self.identifier_value, contact_type="instagram"
            )

        # Ensure only one primary per type/customer
        if self.is_primary:
            CustomerIdentifier.objects.filter(
                customer=self.customer,
                identifier_type=self.identifier_type,
                is_primary=True,
            ).exclude(pk=self.pk).update(is_primary=False)

        super().save(*args, **kwargs)
