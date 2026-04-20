"""DayClosing model."""

from __future__ import annotations

from django.db import models


class DayClosing(models.Model):
    """Registro de fechamento do dia (auditoria)."""

    date = models.DateField("data", unique=True)
    closed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        verbose_name="fechado por",
    )
    closed_at = models.DateTimeField("fechado em", auto_now_add=True)
    notes = models.TextField("observações", blank=True)
    data = models.JSONField(
        "snapshot",
        default=list,
        blank=True,
        help_text="Snapshot de fechamento do dia. Schema definido pela instância.",
    )

    class Meta:
        verbose_name = "fechamento do dia"
        verbose_name_plural = "fechamentos do dia"
        ordering = ["-date"]
        permissions = [("perform_closing", "Pode executar fechamento do dia")]

    def __str__(self):
        return f"Fechamento {self.date}"
