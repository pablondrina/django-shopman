"""
Recipe and RecipeItem models.

Recipe = technical sheet/BOM (Bill of Materials) — defines HOW to make something.
RecipeItem = ingredient/component line (French coefficient method).

Reference: http://techno.boulangerie.free.fr/

vNext: string refs (output_sku, input_sku) replace GenericForeignKey.
"""

from decimal import Decimal

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from shopman.utils.refs import RefField

RECIPE_ITEM_UNIT_VALUES = ["un", "kg", "g", "mg", "L", "ml"]
RECIPE_ITEM_UNIT_ALIASES = {
    "un.": "un",
    "unit": "un",
    "units": "un",
    "l": "L",
    "lt": "L",
    "lts": "L",
    "liter": "L",
    "liters": "L",
    "litro": "L",
    "litros": "L",
}


class Recipe(models.Model):
    """
    Ficha tecnica de producao (BOM).

    Define:
    - output_sku: o que produz (string ref, agnostico)
    - batch_size: rendimento base usado para escalar a ficha técnica
    - steps: etapas de producao (referencia, nao tracking)
    """

    ref = models.SlugField(
        unique=True,
        max_length=50,
        verbose_name=_("Ref"),
        help_text=_("Identificador unico (ex: croissant-v1)"),
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Nome"),
    )
    output_sku = RefField(
        ref_type="SKU",
        max_length=100,
        verbose_name=_("SKU produzido"),
        help_text=_("SKU ao qual esta ficha técnica/BOM se aplica."),
    )
    batch_size = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("1"),
        verbose_name=_("Rendimento base"),
        help_text=_("Quantidade produzida pela ficha técnica base; usada para escalar insumos."),
    )
    steps = models.JSONField(
        default=list,
        blank=True,
        verbose_name=_("Etapas"),
        help_text=_('Etapas de produção. Ex: ["Mistura", "Fermentação", "Modelagem", "Forno"]'),
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Ativa"),
    )
    meta = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Metadados"),
        help_text=_('Metadados da ficha técnica. Ex: {"prep_time_min": 30, "bake_temp_c": 220}'),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Criado em"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Atualizado em"),
    )

    class Meta:
        db_table = "crafting_recipe"
        verbose_name = _("Ficha técnica")
        verbose_name_plural = _("Fichas técnicas")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["output_sku"]),
            models.Index(fields=["is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(batch_size__gt=0),
                name="craft_recipe_batch_positive",
            ),
            models.UniqueConstraint(
                fields=["output_sku"],
                condition=models.Q(is_active=True) & ~models.Q(output_sku=""),
                name="craft_recipe_active_output_uq",
            ),
        ]

    def clean(self):
        super().clean()
        if self.batch_size is not None and self.batch_size <= 0:
            raise ValidationError({"batch_size": _("Deve ser maior que zero.")})
        if self.is_active and self.output_sku:
            self._validate_unique_active_output_sku()
            _validate_output_sku_for_recipe(self.output_sku)
        if self.steps and not isinstance(self.steps, list):
            raise ValidationError({"steps": _("Deve ser uma lista de nomes de etapas.")})
        if self.steps:
            for i, s in enumerate(self.steps):
                if not isinstance(s, str) or not s.strip():
                    raise ValidationError(
                        {"steps": _("Etapa %(step)s deve ser uma string nao-vazia.") % {"step": i + 1}}
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.name} ({self.batch_size} base)"

    def _validate_unique_active_output_sku(self) -> None:
        duplicate = Recipe.objects.filter(
            output_sku=self.output_sku,
            is_active=True,
        )
        if self.pk:
            duplicate = duplicate.exclude(pk=self.pk)
        if duplicate.exists():
            raise ValidationError({
                "output_sku": _(
                    "Já existe uma ficha técnica ativa para este SKU. "
                    "Inative a ficha técnica anterior ou modele uma rota explícita."
                )
            })


class RecipeItem(models.Model):
    """
    Ingrediente de uma ficha tecnica (metodo do coeficiente frances).

    Armazena quantidade para o rendimento base da ficha tecnica (batch_size).
    Coeficiente calculado dinamicamente:
        coefficient = wo.quantity / recipe.batch_size
        ingredient_needed = recipe_item.quantity * coefficient

    Multilevel BOM: se input_sku aponta para algo que tem Recipe propria,
    e um sub-produto. Expansao recursiva com cycle detection (max depth 5).
    """

    class Unit(models.TextChoices):
        UNIT = "un", _("un.")
        KILOGRAM = "kg", _("kg")
        GRAM = "g", _("g")
        MILLIGRAM = "mg", _("mg")
        LITER = "L", _("L")
        MILLILITER = "ml", _("ml")

    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Ficha técnica"),
    )
    input_sku = RefField(
        ref_type="SKU",
        verbose_name=_("Insumo"),
        max_length=100,
        help_text=_("Referencia do material de entrada"),
        db_index=False,
    )
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name=_("Quantidade"),
        help_text=_("Quantidade para o rendimento base da ficha técnica."),
    )
    unit = models.CharField(
        max_length=20,
        choices=Unit.choices,
        default="kg",
        verbose_name=_("Unidade"),
    )
    sort_order = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Ordem"),
    )
    is_optional = models.BooleanField(
        default=False,
        verbose_name=_("Opcional"),
        help_text=_("Ingrediente alternativo"),
    )
    meta = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Metadados"),
    )

    class Meta:
        db_table = "crafting_recipe_item"
        verbose_name = _("Ingrediente")
        verbose_name_plural = _("Ingredientes")
        ordering = ["sort_order"]
        unique_together = [("recipe", "input_sku")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="craft_recipeitem_qty_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(unit__in=RECIPE_ITEM_UNIT_VALUES),
                name="craft_recipeitem_unit_known",
            ),
        ]

    def clean(self):
        super().clean()
        self.unit = normalize_recipe_item_unit(self.unit)
        if self.unit not in self.Unit.values:
            raise ValidationError({"unit": _("Unidade inválida para cálculo da ficha técnica.")})
        product_unit = _catalog_unit_for_sku(self.input_sku)
        if product_unit:
            normalized_product_unit = normalize_recipe_item_unit(product_unit)
            if normalized_product_unit in self.Unit.values and normalized_product_unit != self.unit:
                raise ValidationError({
                    "unit": _(
                        "A unidade do ingrediente deve coincidir com a unidade do SKU cadastrado (%(unit)s)."
                    ) % {"unit": normalized_product_unit}
                })

    def __str__(self) -> str:
        unit_str = f" {self.unit}" if self.unit else ""
        return f"{self.input_sku} ({self.quantity}{unit_str})"


def normalize_recipe_item_unit(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    return RECIPE_ITEM_UNIT_ALIASES.get(raw, RECIPE_ITEM_UNIT_ALIASES.get(raw.lower(), raw))


def _catalog_unit_for_sku(sku: str) -> str:
    info = _catalog_product_info(sku)
    if info is not None:
        return getattr(info, "unit", "") or ""
    try:
        Product = apps.get_model("offerman", "Product")
    except LookupError:
        return ""
    try:
        return Product.objects.only("unit").get(sku=sku).unit or ""
    except Product.DoesNotExist:
        return ""


def _validate_output_sku_for_recipe(sku: str) -> None:
    validation = _catalog_output_validation(sku)
    if validation is not None and not getattr(validation, "valid", True):
        raise ValidationError({
            "output_sku": getattr(validation, "message", "")
            or _("SKU inválido para saída de produção.")
        })

    info = _catalog_product_info(sku)
    if info is not None and getattr(info, "is_bundle", False):
        raise ValidationError({
            "output_sku": _(
                "Combos/bundles são composição comercial em Offerman. "
                "Produza os componentes ou defina uma rota de produção explícita."
            )
        })


def _catalog_product_info(sku: str):
    try:
        from shopman.craftsman.adapters.catalog import get_catalog_backend

        backend = get_catalog_backend()
    except Exception:
        return None

    if hasattr(backend, "get_product"):
        try:
            return backend.get_product(sku)
        except Exception:
            return None
    if hasattr(backend, "get_product_info"):
        try:
            return backend.get_product_info(sku)
        except Exception:
            return None
    return None


def _catalog_output_validation(sku: str):
    try:
        from shopman.craftsman.adapters.catalog import get_catalog_backend

        backend = get_catalog_backend()
    except Exception:
        return None

    if not hasattr(backend, "validate_output_sku"):
        return None
    try:
        return backend.validate_output_sku(sku)
    except Exception:
        return None
