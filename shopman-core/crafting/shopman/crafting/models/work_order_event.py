"""
WorkOrderEvent — Semantic audit trail + idempotency.

Replaces django-simple-history with lightweight, queryable events.
Each mutation creates one event with incremental seq.

Event kinds: planned, adjusted, closed, voided.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class WorkOrderEvent(models.Model):
    """
    Registro imutavel de auditoria.

    - seq: incremental per WorkOrder (0, 1, 2, ...)
    - kind: planned | adjusted | closed | voided
    - payload: JSON with event-specific data
    - idempotency_key: unique, prevents double-close
    """

    class Kind(models.TextChoices):
        PLANNED = "planned", _("Planejado")
        ADJUSTED = "adjusted", _("Ajustado")
        CLOSED = "closed", _("Encerrado")
        VOIDED = "voided", _("Cancelado")

    work_order = models.ForeignKey(
        "crafting.WorkOrder",
        on_delete=models.CASCADE,
        related_name="events",
        verbose_name=_("Ordem"),
    )
    seq = models.PositiveIntegerField(
        verbose_name=_("Sequencia"),
    )
    kind = models.CharField(
        max_length=20,
        choices=Kind.choices,
        verbose_name=_("Tipo"),
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Dados"),
        help_text=_('Dados do evento. Ex: {"produced": 48, "waste": 2}'),
    )
    actor = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Ator"),
    )
    idempotency_key = models.CharField(
        max_length=200,
        unique=True,
        null=True,
        blank=True,
        verbose_name=_("Chave de Idempotencia"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Criado em"),
    )

    class Meta:
        db_table = "crafting_work_order_event"
        verbose_name = _("Evento da Ordem")
        verbose_name_plural = _("Eventos da Ordem")
        unique_together = [("work_order", "seq")]
        ordering = ["work_order", "seq"]

    def __str__(self) -> str:
        return f"#{self.seq} {self.kind} ({self.work_order_id})"
