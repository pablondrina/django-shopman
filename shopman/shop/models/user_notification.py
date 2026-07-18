"""UserNotification — notificação interna por usuário, agnóstica de surface.

Hoje as notificações operacionais são por superfície (SSE por app): quem não
está com a tela aberta não fica sabendo. O broadcast quebra esse modelo — o
gestor precisa receber o pedido de aprovação onde ele estiver, seja no Gestor,
no Hub ou na Produção.

Entrega por SSE no canal ``user-{id}``; qualquer superfície logada escuta o
canal do usuário autenticado.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class NotificationCategory(models.TextChoices):
    BROADCAST = "broadcast", "broadcast"
    PRODUCTION = "production", "produção"
    ORDER = "order", "pedidos"
    SYSTEM = "system", "sistema"


class UserNotification(models.Model):
    """Uma notificação endereçada a uma pessoa, não a uma tela."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name="notifications", verbose_name="usuário",
    )
    category = models.CharField(
        "categoria", max_length=32,
        choices=NotificationCategory.choices, default=NotificationCategory.SYSTEM,
    )
    title = models.CharField("título", max_length=200)
    message = models.TextField("mensagem", blank=True)
    action_url = models.CharField(
        "link", max_length=500, blank=True,
        help_text="Deep link relativo dentro das superfícies de operador",
    )
    action_data = models.JSONField(
        "dados da ação", default=dict, blank=True,
        help_text='Payload da ação, ex: {"broadcast_post_id": 12}',
    )
    is_actionable = models.BooleanField(
        "acionável", default=False,
        help_text="A notificação pede uma decisão, não só informa",
    )
    is_read = models.BooleanField("lida", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField("lida em", null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "notificação"
        verbose_name_plural = "notificações"
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug only
        state = "lida" if self.is_read else "nova"
        return f"[{state}] {self.title}"

    def mark_read(self) -> None:
        """Idempotente: reler não move o carimbo da primeira leitura."""
        if self.is_read:
            return
        self.is_read = True
        self.read_at = timezone.now()
        self.save(update_fields=["is_read", "read_at"])
