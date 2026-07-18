from django.db import models
from django.utils.translation import gettext_lazy as _
from shopman.refs.fields import RefField


class Supplier(models.Model):
    """Fornecedor (lado montante)."""

    ref = RefField(
        ref_type="SUPPLIER",
        unique=True,
        verbose_name=_("Referência"),
        help_text=_("Identificador do fornecedor (ex.: SUP-MOINHO-SP)."),
    )
    name = models.CharField(max_length=200, verbose_name=_("Nome"))
    document = models.CharField(
        max_length=32, blank=True, default="", verbose_name=_("CNPJ/Documento"),
    )
    email = models.EmailField(blank=True, default="", verbose_name=_("E-mail"))
    phone = models.CharField(max_length=32, blank=True, default="", verbose_name=_("Telefone"))
    is_active = models.BooleanField(default=True, db_index=True, verbose_name=_("Ativo"))
    metadata = models.JSONField(default=dict, blank=True, verbose_name=_("Metadados"))
    created_at = models.DateTimeField(auto_now_add=True, verbose_name=_("Criado em"))
    updated_at = models.DateTimeField(auto_now=True, verbose_name=_("Atualizado em"))

    class Meta:
        verbose_name = _("fornecedor")
        verbose_name_plural = _("fornecedores")
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name or self.ref
