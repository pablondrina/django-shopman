"""Product model."""

import uuid as uuid_lib
from decimal import ROUND_HALF_UP, Decimal

from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from simple_history.models import HistoricalRecords
from taggit.managers import TaggableManager


class AvailabilityPolicy(models.TextChoices):
    """Availability policy for stock checking."""

    STOCK_ONLY = "stock_only", _("Somente estoque")
    PLANNED_OK = "planned_ok", _("Aceita planejado")
    DEMAND_OK = "demand_ok", _("Aceita demanda")


class ProductQuerySet(models.QuerySet):
    """Custom QuerySet for Product with publication and sellability filters."""

    def sellable(self):
        """Products that are commercially enabled."""
        return self.filter(is_sellable=True)

    def published(self):
        """Products that are published in the base catalog."""
        return self.filter(is_published=True)


class Product(models.Model):
    """Sellable product."""

    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True, verbose_name=_("UUID"))

    # Identification
    sku = models.CharField(
        _("SKU"),
        max_length=100,
        unique=True,
    )
    name = models.CharField(_("nome"), max_length=200)
    short_description = models.CharField(
        _("descrição curta"),
        max_length=255,
        blank=True,
        help_text=_("Descrição resumida para listagens (máx. 255 caracteres)"),
    )
    long_description = models.TextField(
        _("descrição longa"),
        blank=True,
        help_text=_("Descrição completa do produto"),
    )

    # Keywords for SEO, search, and suggestions
    keywords = TaggableManager(
        blank=True,
        verbose_name=_("palavras-chave"),
        help_text=_("Tags para SEO e busca. Separe por vírgula."),
    )

    # Unit of measure
    unit = models.CharField(
        _("unidade"),
        max_length=20,
        default="un",
        help_text=_("un, kg, lt, etc."),
    )

    # Weight per unit in grams (for display: "~150g a unidade")
    unit_weight_g = models.PositiveIntegerField(
        _("peso por unidade (g)"),
        null=True,
        blank=True,
        help_text=_("Peso aproximado por unidade em gramas. Ex: 150 para pão francês"),
    )

    # Storage tip (short text for conservation guidance)
    storage_tip = models.CharField(
        _("dica de conservação"),
        max_length=300,
        blank=True,
        help_text=_("Breve dica de conservação exibida na página do produto"),
    )

    # Base price (in cents)
    base_price_q = models.BigIntegerField(
        _("preço base"),
        default=0,
        validators=[MinValueValidator(0)],
        help_text=_("Preço base em centavos"),
    )

    # Availability policy (used by Stockman)
    availability_policy = models.CharField(
        _("política de disponibilidade"),
        max_length=20,
        choices=AvailabilityPolicy.choices,
        default=AvailabilityPolicy.PLANNED_OK,
    )

    # Shelf life in days (None = non-perishable, 0 = same day)
    shelf_life_days = models.IntegerField(
        _("validade (dias)"),
        null=True,
        blank=True,
        help_text=_("Validade em dias. Vazio=não perecível, 0=mesmo dia"),
    )

    # Production cycle in hours (how long to produce, used by Stockman/Craftsman for planning)
    production_cycle_hours = models.IntegerField(
        _("ciclo de produção (horas)"),
        null=True,
        blank=True,
        help_text=_("Tempo de produção em horas (ex: 4h para croissant)"),
    )

    # === PUBLICATION & SELLABILITY ===
    is_published = models.BooleanField(
        _("publicado"),
        default=True,
        db_index=True,
        help_text=_("Publicado no catálogo (Não = oculto/descontinuado)"),
    )

    is_sellable = models.BooleanField(
        _("vendável"),
        default=True,
        db_column="is_available",
        db_index=True,
        help_text=_("Permite venda estratégica (Não = insumo ou item pausado)"),
    )

    # Image
    image_url = models.URLField(
        _("URL da imagem"),
        max_length=500,
        blank=True,
        help_text=_("URL da imagem principal do produto (ex: Unsplash, Cloudinary, S3)"),
    )

    # Batch production flag
    is_batch_produced = models.BooleanField(
        _("produção em lote"),
        default=False,
        help_text=_("Produzido em lotes (para Craftsman)"),
    )

    # Metadata
    metadata = models.JSONField(
        _("metadados"),
        default=dict,
        blank=True,
    )

    # Audit
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    # History tracking
    history = HistoricalRecords()

    # Custom manager with QuerySet methods
    objects = ProductQuerySet.as_manager()

    class Meta:
        verbose_name = _("produto")
        verbose_name_plural = _("produtos")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["is_published", "is_sellable"]),
        ]

    def __str__(self):
        return f"{self.sku} - {self.name}"

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            from shopman.offerman.signals import product_created

            product_created.send(sender=self.__class__, instance=self, sku=self.sku)

    @property
    def base_price(self) -> Decimal:
        """Base price in currency units."""
        return Decimal(self.base_price_q) / 100

    @base_price.setter
    def base_price(self, value: Decimal):
        self.base_price_q = int((Decimal(str(value)) * 100).to_integral_value(rounding=ROUND_HALF_UP))

    @property
    def is_perishable(self) -> bool:
        """True if product has a shelf life (perishable)."""
        return self.shelf_life_days is not None

    @property
    def is_bundle(self) -> bool:
        """True if has components (is a bundle/combo)."""
        return self.components.exists()

    @property
    def reference_cost_q(self) -> int | None:
        """
        Production cost in centavos, read from CostBackend.

        Replaces the old reference_cost_q field — cost is now owned by
        the app that knows it (e.g. Craftsman), not stored on Product.
        """
        from shopman.offerman.conf import get_cost_backend

        backend = get_cost_backend()
        if backend is None:
            return None
        return backend.get_cost(self.sku)

    @property
    def margin_percent(self) -> Decimal | None:
        """Margin percentage (if CostBackend provides cost)."""
        cost_q = self.reference_cost_q
        if not cost_q or not self.base_price_q:
            return None
        margin = self.base_price_q - cost_q
        return Decimal(margin * 100 / self.base_price_q).quantize(Decimal("0.1"))

    @property
    def is_hidden(self) -> bool:
        """Compatibility property: True if not published."""
        return not self.is_published

    @is_hidden.setter
    def is_hidden(self, value: bool):
        """Compatibility setter: sets is_published to inverse."""
        self.is_published = not value
