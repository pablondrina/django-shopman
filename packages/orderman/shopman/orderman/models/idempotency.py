from __future__ import annotations

from django.db import models
from django.utils.translation import gettext_lazy as _


class IdempotencyKey(models.Model):
    """Dedupe/replay guard para operações idempotentes."""

    scope = models.CharField(_("escopo"), max_length=64)
    key = models.CharField(_("chave"), max_length=128)

    status = models.CharField(
        _("status"),
        max_length=16,
        choices=[
            ("in_progress", _("em andamento")),
            ("done", _("concluído")),
            ("failed", _("falhou")),
        ],
        default="in_progress",
    )

    response_code = models.IntegerField(_("código de resposta"), null=True, blank=True)
    response_body = models.JSONField(_("corpo da resposta"), null=True, blank=True)

    expires_at = models.DateTimeField(_("expira em"), null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(_("criado em"), auto_now_add=True)

    class Meta:
        app_label = "orderman"
        verbose_name = _("chave de idempotência")
        verbose_name_plural = _("chaves de idempotência")
        constraints = [
            models.UniqueConstraint(
                fields=["scope", "key"],
                name="ord_uniq_idempotency_scope_key",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.key}"
