"""CustomerAddress model (Google Places structured)."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class AddressLabel(models.TextChoices):
    """Standard address labels (iFood-style)."""

    HOME = "home", _("Casa")
    WORK = "work", _("Trabalho")
    OTHER = "other", _("Outro")


class CustomerAddress(models.Model):
    """Customer address (structured via Google Places)."""

    customer = models.ForeignKey(
        "guestman.Customer",
        on_delete=models.CASCADE,
        related_name="addresses",
        verbose_name=_("cliente"),
    )

    # Label (Home, Work, Custom)
    label = models.CharField(
        _("rótulo"),
        max_length=20,
        choices=AddressLabel.choices,
        default=AddressLabel.HOME,
    )
    label_custom = models.CharField(
        _("rótulo personalizado"),
        max_length=50,
        blank=True,
        help_text=_("Rótulo personalizado quando tipo=outro"),
    )

    # Google Places data
    place_id = models.CharField(
        _("ID do Google Places"),
        max_length=255,
        blank=True,
        help_text=_("ID do Google Places"),
    )
    formatted_address = models.CharField(
        _("endereço formatado"),
        max_length=500,
        help_text=_("Endereço completo formatado"),
    )

    # Structured components (from Google Places)
    street_number = models.CharField(_("número"), max_length=20, blank=True)
    route = models.CharField(
        _("logradouro"),
        max_length=200,
        blank=True,
        help_text=_("Nome da rua"),
    )
    neighborhood = models.CharField(_("bairro"), max_length=100, blank=True)
    city = models.CharField(_("cidade"), max_length=100, blank=True)
    state = models.CharField(_("estado"), max_length=50, blank=True)
    state_code = models.CharField(
        _("UF"),
        max_length=5,
        blank=True,
        help_text=_("Sigla do estado"),
    )
    postal_code = models.CharField(
        _("CEP"),
        max_length=20,
        blank=True,
        help_text=_("Código postal"),
    )
    country = models.CharField(_("país"), max_length=100, default="Brasil")
    country_code = models.CharField(_("código do país"), max_length=5, default="BR")

    # Coordinates
    latitude = models.DecimalField(
        _("latitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    longitude = models.DecimalField(
        _("longitude"),
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )

    # Complement (not from Google Places)
    complement = models.CharField(
        _("complemento"),
        max_length=100,
        blank=True,
        help_text=_("Apto, bloco, referência"),
    )

    # Delivery instructions
    delivery_instructions = models.TextField(
        _("instruções de entrega"),
        blank=True,
        help_text=_("Instruções para o entregador"),
    )

    # Control
    is_default = models.BooleanField(_("padrão"), default=False)
    is_verified = models.BooleanField(
        _("verificado"),
        default=False,
        help_text=_("Endereço verificado via Google Places"),
    )

    # Audit
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("endereço")
        verbose_name_plural = _("endereços")
        ordering = ["-is_default", "label"]

    def __str__(self):
        label_display = (
            self.label_custom
            if self.label == AddressLabel.OTHER and self.label_custom
            else self.get_label_display()
        )
        addr = self.formatted_address[:50] if self.formatted_address else ""
        return f"{label_display}: {addr}"

    @property
    def display_label(self) -> str:
        """Label for display."""
        if self.label == AddressLabel.OTHER and self.label_custom:
            return self.label_custom
        return self.get_label_display()

    @property
    def short_address(self) -> str:
        """Short address for lists. Safe when fields are empty."""
        parts = []
        if self.route:
            parts.append(self.route)
        if self.street_number:
            parts.append(self.street_number)
        if self.neighborhood:
            parts.append(f"- {self.neighborhood}")
        return " ".join(parts) if parts else self.formatted_address[:60]

    def save(self, *args, **kwargs):
        if self.is_default:
            CustomerAddress.objects.filter(
                customer=self.customer, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
