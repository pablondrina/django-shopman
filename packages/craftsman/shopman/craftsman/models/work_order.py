"""
WorkOrder model (vNext).

4 states: planned, started, finished, void.
3 quantities: planned, started, finished.
1 rev: optimistic concurrency.

Business logic lives in services, not in the model.
The model encapsulates invariants and data integrity.
"""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class WorkOrder(models.Model):
    """
    Ordem de producao.

    Lifecycle:
        planned ---> started ---> finished
            |             |
            +------------>+
            |
            +-----> void

    The three quantities:
        quantity: planned_qty (mutable via craft.adjust while planned)
        started_qty: quantity effectively sent into production
        finished: final output quantity (set once via craft.finish)
    """

    class Status(models.TextChoices):
        PLANNED = "planned", _("Planejada")
        STARTED = "started", _("Iniciada")
        FINISHED = "finished", _("Concluída")
        VOID = "void", _("Cancelada")

    ref = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        verbose_name=_("Referência"),
    )
    recipe = models.ForeignKey(
        "craftsman.Recipe",
        on_delete=models.PROTECT,
        related_name="work_orders",
        verbose_name=_("Ficha técnica"),
    )
    output_sku = models.CharField(
        max_length=100,
        verbose_name=_("Produto"),
        help_text=_("Copiado da Recipe no plan"),
    )

    # The quantitative trilogy
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name=_("Quantidade Planejada"),
        help_text=_("Planejado atual (mutavel via adjust enquanto planned)"),
    )
    finished = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name=_("Quantidade Concluída"),
        help_text=_("Set no finish, imutavel depois"),
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PLANNED,
        verbose_name=_("Status"),
    )
    rev = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Revisao"),
        help_text=_("Optimistic concurrency counter"),
    )

    target_date = models.DateField(
        null=True,
        blank=True,
        verbose_name=_("Data Agendada"),
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Iniciada em"),
    )
    finished_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Concluída em"),
    )

    # String refs (agnostic — no FK to external models)
    source_ref = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Origem"),
        help_text=_("'order:789', 'forecast:Q1'"),
    )
    position_ref = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Posição"),
        help_text=_("Ref da Position no Stockman (ex: 'producao')"),
    )
    operator_ref = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Responsavel"),
        help_text=_("'user:joao'"),
    )

    meta = models.JSONField(
        default=dict,
        blank=True,
        verbose_name=_("Metadados"),
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Criado em"),
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Atualizado em"),
    )

    class Meta:
        db_table = "crafting_work_order"
        verbose_name = _("Ordem de Produção")
        verbose_name_plural = _("Produção")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "target_date"]),
            models.Index(fields=["output_sku", "status"]),
            models.Index(fields=["target_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="craft_wo_quantity_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ref} - {self.recipe.name}" if self.ref else f"WO-{self.pk}"

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": _("Deve ser maior que zero.")})

    def save(self, *args, **kwargs):
        """Auto-generate ref via RefSequence if blank."""
        if not self.ref:
            self.ref = self._generate_ref()
        # full_clean only on creation/full save — services use
        # save(update_fields=[...]) and validate in the service layer.
        if not kwargs.get("update_fields"):
            self.full_clean()
        super().save(*args, **kwargs)

    def _generate_ref(self) -> str:
        """Generate unique ref: WO-YYYY-NNNNN."""
        from shopman.craftsman.models.sequence import RefSequence

        year = timezone.now().year
        prefix = f"WO-{year}"
        next_num = RefSequence.next_value(prefix)
        return f"{prefix}-{next_num:05d}"

    # ── Properties ──────────────────────────────────────────────

    @property
    def loss(self) -> Decimal | None:
        """Quantity lost between what entered production and what finished."""
        if self.finished is None:
            return None
        base_qty = self.started_qty or self.quantity
        return max(base_qty - self.finished, Decimal("0"))

    @property
    def yield_rate(self) -> Decimal | None:
        """Efficiency: finished_qty / started_qty (or planned if not started)."""
        if self.finished is None:
            return None
        base_qty = self.started_qty or self.quantity
        if not base_qty:
            return None
        return self.finished / base_qty

    @property
    def planned_qty(self) -> Decimal:
        """Canonical planned quantity projection."""
        return self.quantity

    @property
    def started_qty(self) -> Decimal | None:
        """Latest quantity that effectively entered production."""
        event = self.events.filter(kind="started").order_by("-seq").only("payload").first()
        if not event:
            return None
        return Decimal(str(event.payload.get("quantity", "0")))

    @property
    def finished_qty(self) -> Decimal | None:
        """Canonical finished quantity projection."""
        return self.finished
