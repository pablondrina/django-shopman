"""
Recipe and RecipeItem models.

Recipe = BOM (Bill of Materials) — defines HOW to make something.
RecipeItem = Ingredient (French coefficient method).

Reference: http://techno.boulangerie.free.fr/

vNext: string refs (output_ref, input_ref) replace GenericForeignKey.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import gettext_lazy as _
from shopman.refs.fields import RefField


class Recipe(models.Model):
    """
    Receita de producao (BOM).

    Define:
    - output_ref: o que produz (string ref, agnostico)
    - batch_size: quantidade por batelada
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
    output_ref = models.CharField(
        max_length=100,
        verbose_name=_("Produto de Saida"),
        help_text=_("Referencia do produto (ex: SKU, slug)"),
    )
    batch_size = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=Decimal("1"),
        verbose_name=_("Tamanho do Lote"),
        help_text=_("Unidades produzidas por batelada"),
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
        help_text=_('Metadados da receita. Ex: {"prep_time_min": 30, "bake_temp_c": 220}'),
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
        verbose_name = _("Receita")
        verbose_name_plural = _("Receitas")
        ordering = ["name"]
        indexes = [
            models.Index(fields=["output_ref"]),
            models.Index(fields=["is_active"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(batch_size__gt=0),
                name="craft_recipe_batch_positive",
            ),
        ]

    def clean(self):
        super().clean()
        if self.batch_size is not None and self.batch_size <= 0:
            raise ValidationError({"batch_size": _("Deve ser maior que zero.")})
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
        return f"{self.name} ({self.batch_size}x)"


class RecipeItem(models.Model):
    """
    Ingrediente de uma receita (metodo do coeficiente frances).

    Armazena quantidade para a RECEITA BASE (batch_size).
    Coeficiente calculado dinamicamente:
        coefficient = wo.quantity / recipe.batch_size
        ingredient_needed = recipe_item.quantity * coefficient

    Multilevel BOM: se input_ref aponta para algo que tem Recipe propria,
    e um sub-produto. Expansao recursiva com cycle detection (max depth 5).
    """

    recipe = models.ForeignKey(
        Recipe,
        on_delete=models.CASCADE,
        related_name="items",
        verbose_name=_("Receita"),
    )
    input_ref = RefField(
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
        help_text=_("Quantidade por batch_size"),
    )
    unit = models.CharField(
        max_length=20,
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
        unique_together = [("recipe", "input_ref")]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="craft_recipeitem_qty_positive",
            ),
        ]

    def __str__(self) -> str:
        unit_str = f" {self.unit}" if self.unit else ""
        return f"{self.input_ref} ({self.quantity}{unit_str})"
