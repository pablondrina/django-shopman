from django.db import models
from django.utils.translation import gettext_lazy as _


class SupplierMaterialCost(models.Model):
    """Custo de um insumo por fornecedor, em centavos.

    Uma linha por par (fornecedor, insumo). ``is_preferred`` marca o custo
    canônico daquele insumo — é ele que alimenta o custeio (CostBackend) e o
    custo de receita. Histórico de preço fica para uma fase futura.
    """

    supplier = models.ForeignKey(
        "buyman.Supplier", on_delete=models.CASCADE, related_name="material_costs",
        verbose_name=_("Fornecedor"),
    )
    material = models.ForeignKey(
        "buyman.Material", on_delete=models.CASCADE, related_name="supplier_costs",
        verbose_name=_("Insumo"),
    )
    cost_q = models.BigIntegerField(
        verbose_name=_("Custo (centavos)"),
        help_text=_("Custo por unidade do insumo, em centavos."),
    )
    is_preferred = models.BooleanField(
        default=False, verbose_name=_("Preferencial"),
        help_text=_("Marca o custo canônico deste insumo (alimenta o custeio)."),
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        verbose_name = _("Custo de insumo por fornecedor")
        verbose_name_plural = _("Custos de insumo por fornecedor")
        ordering = ["material", "supplier"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "material"],
                name="buyman_supplier_material_unique",
            ),
            models.UniqueConstraint(
                fields=["material"],
                condition=models.Q(is_preferred=True),
                name="buyman_one_preferred_cost_per_material",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.material_id}@{self.supplier_id}: {self.cost_q}"
