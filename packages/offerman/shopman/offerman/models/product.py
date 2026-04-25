"""Product model."""

import uuid as uuid_lib
from decimal import ROUND_HALF_UP, Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _
from shopman.offerman.nutrition import NUTRIENT_FIELDS, NutritionFacts
from shopman.utils.refs import RefField
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
    sku = RefField(
        ref_type="SKU",
        verbose_name=_("SKU"),
        max_length=100,
        unique=True,
        db_index=False,
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

    # Ingredients list (human text, pt-BR, decreasing weight order — ANVISA).
    # Authored manually OR materialized from Recipe via
    # shopman.shop.services.nutrition_from_recipe.
    ingredients_text = models.TextField(
        _("ingredientes"),
        blank=True,
        help_text=_(
            "Lista de ingredientes em ordem decrescente de peso (ANVISA). "
            "Ex: Farinha de trigo, água, fermento natural, sal marinho."
        ),
    )

    # Per-serving nutritional facts.
    # Schema is driven by the ``NutritionFacts`` dataclass
    # (``shopman.offerman.nutrition``). Admin uses a dedicated form;
    # never edit as raw JSON.
    nutrition_facts = models.JSONField(
        _("informações nutricionais"),
        default=dict,
        blank=True,
        help_text=_("Tabela nutricional por porção (gerenciada via form dedicado)."),
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

    def clean(self):
        """Validate ANVISA invariants on ``nutrition_facts``.

        - If any nutrient is present, ``serving_size_g`` is required.
        - All numeric values are ≥ 0.
        - ``trans_fat_g ≤ total_fat_g``, ``saturated_fat_g ≤ total_fat_g``,
          ``sugars_g ≤ carbohydrates_g``.
        """
        super().clean()
        self._validate_nutrition_facts()

    def _validate_nutrition_facts(self):
        facts = self.nutrition_facts or {}
        if not facts:
            return
        if not isinstance(facts, dict):
            raise ValidationError(
                {"nutrition_facts": _("Deve ser um dicionário.")}
            )

        try:
            nf = NutritionFacts.from_dict(facts)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                {"nutrition_facts": _("Schema inválido: %(err)s") % {"err": exc}}
            ) from exc

        if nf is None:
            return

        # Any nutrient requires serving_size_g > 0.
        if nf.has_any_nutrient and nf.serving_size_g <= 0:
            raise ValidationError(
                {"nutrition_facts": _(
                    "Informe a porção (g) quando qualquer nutriente estiver preenchido."
                )}
            )

        # Non-negative values.
        for field_name in NUTRIENT_FIELDS:
            value = getattr(nf, field_name)
            if value is not None and value < 0:
                raise ValidationError(
                    {"nutrition_facts": _(
                        "%(f)s não pode ser negativo."
                    ) % {"f": field_name}}
                )
        if nf.servings_per_container < 1:
            raise ValidationError(
                {"nutrition_facts": _("Porções por embalagem deve ser ≥ 1.")}
            )

        # Structural sub-totals.
        if (
            nf.trans_fat_g is not None
            and nf.total_fat_g is not None
            and nf.trans_fat_g > nf.total_fat_g
        ):
            raise ValidationError(
                {"nutrition_facts": _(
                    "Gorduras trans não podem exceder gorduras totais."
                )}
            )
        if (
            nf.saturated_fat_g is not None
            and nf.total_fat_g is not None
            and nf.saturated_fat_g > nf.total_fat_g
        ):
            raise ValidationError(
                {"nutrition_facts": _(
                    "Gorduras saturadas não podem exceder gorduras totais."
                )}
            )
        if (
            nf.sugars_g is not None
            and nf.carbohydrates_g is not None
            and nf.sugars_g > nf.carbohydrates_g
        ):
            raise ValidationError(
                {"nutrition_facts": _(
                    "Açúcares não podem exceder carboidratos."
                )}
            )

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
