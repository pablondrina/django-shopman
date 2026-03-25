from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .session import DecimalEncoder


class Directive(models.Model):
    """Tarefa assíncrona (at-least-once)."""

    topic = models.CharField(_("tópico"), max_length=64, db_index=True)
    status = models.CharField(
        _("status"),
        max_length=16,
        choices=[
            ("queued", _("em fila")),
            ("running", _("em execução")),
            ("done", _("concluído")),
            ("failed", _("falhou")),
        ],
        default="queued",
        db_index=True,
    )
    payload = models.JSONField(
        _("payload"), default=dict, blank=True, encoder=DecimalEncoder,
        help_text=_('Dados da tarefa. Schema depende do topic. Ex: stock.hold → {"sku": "PAO-FRANCES", "qty": 10}'),
    )

    attempts = models.IntegerField(_("tentativas"), default=0)
    available_at = models.DateTimeField(_("disponível em"), default=timezone.now, db_index=True)
    last_error = models.TextField(_("último erro"), blank=True, default="")

    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)
    started_at = models.DateTimeField(_("iniciado em"), null=True, blank=True)
    updated_at = models.DateTimeField(_("atualizado em"), auto_now=True)

    class Meta:
        app_label = "ordering"
        verbose_name = _("diretiva")
        verbose_name_plural = _("diretivas")

    def __str__(self) -> str:
        if self.pk:
            return f"Diretiva #{self.pk} ({self.topic})"
        return "Nova diretiva"
