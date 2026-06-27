from django.db import models
from django.utils.translation import gettext_lazy as _
from shopman.refs.fields import RefField


class Material(models.Model):
    """Item master de um insumo (material de compra).

    Metadado canônico de um insumo não-vendável — nome, unidade-base, validade
    padrão. Distinto do catálogo de venda do Offerman (só produtos vendáveis):
    aqui mora o lado montante (insumos consumidos na produção).
    """

    class Unit(models.TextChoices):
        UNIT = "un", _("unidade")
        KG = "kg", _("quilograma")
        G = "g", _("grama")
        L = "l", _("litro")
        ML = "ml", _("mililitro")

    sku = RefField(
        ref_type="SKU",
        unique=True,
        verbose_name=_("SKU"),
        help_text=_("Identificador do insumo (ex.: INS-FARINHA-T65)."),
    )
    name = models.CharField(max_length=200, verbose_name=_("Nome"))
    unit = models.CharField(
        max_length=8, choices=Unit.choices, default=Unit.UNIT, verbose_name=_("Unidade"),
    )
    shelf_life_days = models.IntegerField(
        null=True, blank=True, verbose_name=_("Validade padrão (dias)"),
        help_text=_("Validade padrão do insumo em dias. Vazio = não perecível."),
    )
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Ativo"))
    metadata = models.JSONField(
        default=dict, blank=True, verbose_name=_("Metadados"),
        help_text=_("Perfil opcional (nutrição, alérgenos, etc.)."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        verbose_name = _("Insumo")
        verbose_name_plural = _("Insumos")
        ordering = ["sku"]

    @property
    def is_perishable(self) -> bool:
        return self.shelf_life_days is not None

    def __str__(self) -> str:
        return f"{self.sku} — {self.name}"
