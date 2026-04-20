"""
ContactPoint model - Customer contact points (WhatsApp, phone, email).
"""

import uuid

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class ContactPoint(models.Model):
    """
    Customer contact point.

    Types: WhatsApp, phone, email.
    Each type can have one "primary".

    Verification methods:
    - CHANNEL_ASSERTED: Channel already verified (e.g., WhatsApp via Manychat)
    - OTP_WHATSAPP: Code sent via WhatsApp (via Auth)
    - OTP_SMS: Code sent via SMS (via Auth)
    - EMAIL_LINK: Verification link by email (via Auth)
    - MANUAL: Manually verified by staff

    Rules (enforced by Gates):
    - (type, value_normalized) is globally unique
    - Only 1 is_primary=True per (customer, type)
    """

    class Type(models.TextChoices):
        WHATSAPP = "whatsapp", _("WhatsApp")
        PHONE = "phone", _("Telefone (voz/SMS)")
        EMAIL = "email", _("Email")
        INSTAGRAM = "instagram", _("Instagram")

    class VerificationMethod(models.TextChoices):
        UNVERIFIED = "unverified", _("Não verificado")
        CHANNEL_ASSERTED = "channel_asserted", _("Verificado pelo canal")
        OTP_WHATSAPP = "otp_whatsapp", _("OTP via WhatsApp")
        OTP_SMS = "otp_sms", _("OTP via SMS")
        EMAIL_LINK = "email_link", _("Link por email")
        MANUAL = "manual", _("Manual (equipe)")

    # Identification
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        "guestman.Customer",
        on_delete=models.CASCADE,
        related_name="contact_points",
        verbose_name=_("cliente"),
    )

    # Type and value
    type = models.CharField(
        _("tipo"),
        max_length=20,
        choices=Type.choices,
    )
    value_normalized = models.CharField(
        _("valor normalizado"),
        max_length=255,
        db_index=True,
        help_text=_("Telefone em E.164 (+5541999998888) ou email em minúsculas."),
    )
    value_display = models.CharField(
        _("valor para exibição"),
        max_length=255,
        blank=True,
        help_text=_("Formato amigável para exibição."),
    )

    # Status
    is_primary = models.BooleanField(_("principal"), default=False)
    is_verified = models.BooleanField(_("verificado"), default=False)

    # Verification
    verification_method = models.CharField(
        _("método de verificação"),
        max_length=20,
        choices=VerificationMethod.choices,
        default=VerificationMethod.UNVERIFIED,
    )
    verified_at = models.DateTimeField(_("verificado em"), null=True, blank=True)
    verification_ref = models.CharField(
        _("referência de verificação"),
        max_length=255,
        blank=True,
        help_text=_("Referência externa (ex: Manychat subscriber_id)."),
    )

    # Timestamps
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        db_table = "customers_contact_point"
        verbose_name = _("contato")
        verbose_name_plural = _("contatos")
        ordering = ["-is_primary", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["type", "value_normalized"],
                name="customers_unique_contact_value",
            ),
            models.UniqueConstraint(
                fields=["customer", "type"],
                condition=models.Q(is_primary=True),
                name="customers_unique_primary_per_type",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "type", "is_primary"]),
            models.Index(fields=["type", "value_normalized"]),
        ]

    def __str__(self):
        verified = "V" if self.is_verified else "o"
        primary = " [primary]" if self.is_primary else ""
        return f"{verified} {self.type}: {self.value_masked}{primary}"

    @property
    def value_masked(self) -> str:
        """Masked value for safe display."""
        if self.type == self.Type.EMAIL:
            parts = self.value_normalized.split("@")
            if len(parts) == 2:
                local = parts[0]
                domain = parts[1]
                masked = local[0] + "***" + local[-1] if len(local) > 2 else "***"
                return f"{masked}@{domain}"
            return "***@***"
        else:
            if len(self.value_normalized) > 4:
                return "***" + self.value_normalized[-4:]
            return "****"

    def save(self, *args, **kwargs):
        # Normalize value
        self.value_normalized = self.normalize_value(self.value_normalized, self.type)

        # First of type = primary
        auto_promoted = False
        if not self.pk:
            exists = ContactPoint.objects.filter(
                customer=self.customer,
                type=self.type,
            ).exists()
            if not exists:
                self.is_primary = True
                auto_promoted = True

        super().save(*args, **kwargs)

        # Sync to Customer cache when auto-promoted to primary
        if auto_promoted:
            self._sync_to_customer()

    @staticmethod
    def normalize_value(value: str, contact_type: str | None = None) -> str:
        """
        Normalize contact value to E.164 format.

        Delegates to shopman.utils.normalize_phone for consistent normalization
        across the entire package.
        """
        from shopman.guestman.utils import normalize_phone

        return normalize_phone(value, contact_type=contact_type)

    def set_as_primary(self):
        """
        Set this contact as primary for its type.

        Also syncs the Customer cache field (phone/email) so that
        lookups via CustomerService.get_by_phone/email stay consistent.
        """
        with transaction.atomic():
            ContactPoint.objects.filter(
                customer=self.customer,
                type=self.type,
                is_primary=True,
            ).exclude(pk=self.pk).update(is_primary=False)

            self.is_primary = True
            self.save(update_fields=["is_primary", "updated_at"])

            self._sync_to_customer()

    def _sync_to_customer(self):
        """
        Reverse sync: propagate primary ContactPoint value to Customer cache field.

        Maps ContactPoint.Type → Customer field:
        - PHONE / WHATSAPP → Customer.phone
        - EMAIL → Customer.email
        """
        field_map = {
            self.Type.PHONE: "phone",
            self.Type.WHATSAPP: "phone",
            self.Type.EMAIL: "email",
        }
        customer_field = field_map.get(self.type)
        if not customer_field:
            return

        from shopman.guestman.models.customer import Customer
        Customer.objects.filter(pk=self.customer_id).update(
            **{customer_field: self.value_normalized}
        )

    def mark_verified(self, method: str, ref: str | None = None):
        """Mark contact as verified."""
        valid = {v.value for v in self.VerificationMethod}
        if method not in valid:
            raise ValueError(
                f"Método de verificação inválido: {method!r}. Válidos: {sorted(valid)}"
            )
        self.is_verified = True
        self.verification_method = method
        self.verified_at = timezone.now()
        if ref:
            self.verification_ref = ref
        self.save(
            update_fields=[
                "is_verified",
                "verification_method",
                "verified_at",
                "verification_ref",
                "updated_at",
            ]
        )
