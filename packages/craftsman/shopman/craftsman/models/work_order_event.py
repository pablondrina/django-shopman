"""
WorkOrderEvent — Semantic audit trail + idempotency.

Replaces django-simple-history with lightweight, queryable events.
Each mutation creates one event with incremental seq.

Event kinds: planned, adjusted, started, finished, voided.

Canonical payload schemas per kind:

    planned:
        quantity: str       — planned quantity
        recipe: str         — recipe code
        output_sku: str     — produced SKU/ref
        target_date: str — planned date
        source_ref: str     — upstream source/request
        position_ref: str   — planned station/post
        operator_ref: str   — planned responsible actor

    adjusted:
        from: str           — previous quantity
        to: str             — new quantity
        reason: str         — adjustment reason

    started:
        quantity: str       — quantity sent into production
        operator_ref: str   — who is producing (e.g. "user:joao")
        position_ref: str   — where (e.g. "producao")
        note: str           — optional note
        implicit: bool      — True if auto-started by finish

    finished:
        finished_qty: str   — actual output quantity
        planned_qty: str    — originally planned quantity
        started_qty: str    — quantity that entered production
        loss_qty: str       — waste/loss quantity
        output_sku: str     — produced SKU/ref
        target_date: str — production date
        source_ref: str     — upstream source/request
        position_ref: str   — station/post
        operator_ref: str   — responsible actor

    voided:
        reason: str         — cancellation reason

WorkOrderItem provides the material ledger (requirement, consumption,
output, waste). Events are the semantic trail of what happened and why.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class WorkOrderEvent(models.Model):
    """
    Immutable audit record for WorkOrder state transitions.

    - seq: incremental per WorkOrder (0, 1, 2, ...)
    - kind: planned | adjusted | started | finished | voided
    - payload: JSON with event-specific data (see module docstring for schemas)
    - idempotency_key: unique, prevents duplicate finish
    """

    class Kind(models.TextChoices):
        PLANNED = "planned", _("Planejado")
        ADJUSTED = "adjusted", _("Ajustado")
        STARTED = "started", _("Iniciado")
        FINISHED = "finished", _("Finalizado")
        VOIDED = "voided", _("Cancelado")

    work_order = models.ForeignKey(
        "craftsman.WorkOrder",
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
        help_text=_("Dados do evento. Schema por kind documentado no módulo."),
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
