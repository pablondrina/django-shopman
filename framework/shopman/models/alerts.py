"""OperatorAlert model."""

from __future__ import annotations

from django.db import models


class OperatorAlert(models.Model):
    """Alerta operacional — falhas, estoque baixo, pagamentos pendentes."""

    TYPE_CHOICES = [
        ("notification_failed", "Notificação falhou"),
        ("payment_failed", "Pagamento falhou"),
        ("stock_discrepancy", "Discrepância de estoque"),
        ("payment_after_cancel", "Pagamento após cancelamento"),
        ("stock_low", "Estoque baixo"),
        ("marketplace_rejected_unavailable", "Marketplace rejeitado: indisponível"),
        ("marketplace_rejected_oos", "Marketplace rejeitado: sem estoque"),
        ("pos_rejected_unavailable", "POS rejeitado: produto indisponível"),
    ]
    SEVERITY_CHOICES = [
        ("warning", "Aviso"),
        ("error", "Erro"),
        ("critical", "Crítico"),
    ]

    type = models.CharField("tipo", max_length=50, choices=TYPE_CHOICES)
    severity = models.CharField("severidade", max_length=10, choices=SEVERITY_CHOICES, default="warning")
    message = models.TextField("mensagem")
    order_ref = models.CharField("ref do pedido", max_length=50, blank=True)
    acknowledged = models.BooleanField("reconhecido", default=False)
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "alerta operacional"
        verbose_name_plural = "alertas operacionais"
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.get_severity_display()}] {self.message[:80]}"
