"""CustomerPreference model."""

from decimal import Decimal

from django.db import models
from django.utils.translation import gettext_lazy as _


class PreferenceType(models.TextChoices):
    """Preference types."""

    EXPLICIT = "explicit", _("Explícita")  # Customer declared
    INFERRED = "inferred", _("Inferida")  # System detected
    RESTRICTION = "restriction", _("Restrição")  # Allergy, diet, etc.


class CustomerPreference(models.Model):
    """Customer preference."""

    customer = models.ForeignKey(
        "attending.Customer",
        on_delete=models.CASCADE,
        related_name="preferences",
        verbose_name=_("cliente"),
    )

    # Type and category
    preference_type = models.CharField(
        _("tipo"),
        max_length=20,
        choices=PreferenceType.choices,
        default=PreferenceType.EXPLICIT,
    )
    category = models.CharField(
        _("categoria"),
        max_length=50,
        help_text=_("Categoria da preferência (ex: 'dietética', 'sabor', 'embalagem')"),
    )

    # Key-value
    key = models.CharField(
        _("chave"),
        max_length=100,
        help_text=_("Nome da preferência (ex: 'sem_lactose', 'pao_favorito')"),
    )
    value = models.JSONField(
        _("valor"),
        default=dict,
        help_text=_("Valor da preferência (pode ser bool, string, lista, etc.)"),
    )

    # Confidence (for inferred)
    confidence = models.DecimalField(
        _("confiança"),
        max_digits=3,
        decimal_places=2,
        default=Decimal("1.00"),
        help_text=_("0.00 a 1.00 - confiança na preferência inferida"),
    )

    # Context
    source = models.CharField(
        _("origem"),
        max_length=100,
        blank=True,
        help_text=_("Origem da preferência (ex: 'pedido:123', 'formulário', 'chat')"),
    )
    notes = models.TextField(_("observações"), blank=True)

    # Audit
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        verbose_name = _("preferência")
        verbose_name_plural = _("preferências")
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "category", "key"],
                name="guestman_unique_preference",
            ),
        ]
        ordering = ["category", "key"]

    def __str__(self):
        return f"{self.customer.ref}: {self.category}.{self.key}"
