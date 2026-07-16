"""OperatorAlert model."""

from __future__ import annotations

from django.db import models


class OperatorAlert(models.Model):
    """Alerta operacional — falhas, estoque baixo, pagamentos pendentes."""

    TYPE_CHOICES = [
        ("notification_failed", "Notificação falhou"),
        ("payment_failed", "Pagamento falhou"),
        ("payment_insufficient", "Pagamento abaixo do total"),
        ("payment_reconciliation_failed", "Reconciliação de pagamento falhou"),
        ("webhook_failed", "Webhook falhou"),
        ("stock_discrepancy", "Discrepância de estoque"),
        ("payment_after_cancel", "Pagamento após cancelamento"),
        ("stock_low", "Estoque baixo"),
        ("marketplace_rejected_unavailable", "Marketplace rejeitado: indisponível"),
        ("marketplace_rejected_oos", "Marketplace rejeitado: sem estoque"),
        ("coupon_over_redeemed", "Cupom resgatado acima do limite"),
        ("pos_rejected_unavailable", "POS rejeitado: produto indisponível"),
        ("stale_new_order", "Pedido parado aguardando confirmação"),
        ("production_late", "Produção atrasada"),
        ("production_low_yield", "Produção com yield baixo"),
        ("production_stock_short", "Produção sem insumo suficiente"),
        ("directive_failed_spike", "Tarefas de fundo falhando"),
        ("directive_backlog", "Fila de tarefas de fundo acumulada"),
        ("directive_worker_stale", "Worker de tarefas de fundo parado"),
        ("lifecycle_phase_stuck", "Fase do pedido travada"),
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
