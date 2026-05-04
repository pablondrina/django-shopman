"""POS tab models."""

from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models


class POSTab(models.Model):
    """Physical/digital POS tab identified by an 8-digit code."""

    code = models.CharField(
        "código",
        max_length=8,
        unique=True,
        validators=[RegexValidator(r"^\d{8}$", "Use exatamente 8 dígitos.")],
        help_text="Código armazenado com 8 dígitos. Ex: 00001007.",
    )
    label = models.CharField("rótulo", max_length=64, blank=True, default="")
    is_active = models.BooleanField("ativa", default=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "POS tab"
        verbose_name_plural = "POS tabs"
        ordering = ["code"]

    @property
    def display_code(self) -> str:
        return self.code.lstrip("0") or "0"

    def __str__(self) -> str:
        return self.label or self.display_code
