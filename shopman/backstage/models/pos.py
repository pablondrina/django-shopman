"""POS tab models."""

from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models


class POSTab(models.Model):
    """Physical/digital POS tab identified by an operator-facing reference."""

    ref = models.CharField(
        "referência",
        max_length=64,
        unique=True,
        validators=[RegexValidator(r"^(?!\s*$)[^/\\?#%\r\n\t]{1,64}$", "Use até 64 caracteres, sem barras ou caracteres de URL.")],
        help_text="Referência curta da comanda. Números continuam normalizados com 8 dígitos; texto livre é aceito para identificação operacional.",
    )
    label = models.CharField("rótulo", max_length=120, blank=True, default="")
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "POS tab"
        verbose_name_plural = "POS tabs"
        ordering = ["ref"]

    @property
    def display_ref(self) -> str:
        if self.label:
            return self.label
        if self.ref.isdigit():
            return self.ref.lstrip("0") or "0"
        return self.ref

    def __str__(self) -> str:
        return self.label or self.display_ref
