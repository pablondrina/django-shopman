"""
WorkOrder model (vNext).

3 states: open, done, void.
2 numbers: quantity (mutable target), produced (set on close).
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
        open ---> done  (via craft.close)
          |
          +-----> void  (via craft.void)

    The two numbers:
        quantity: target (mutable via craft.adjust)
        produced: actual output (set once via craft.close)
    """

    class Status(models.TextChoices):
        OPEN = "open", _("Aberta")
        DONE = "done", _("Concluida")
        VOID = "void", _("Cancelada")

    code = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        verbose_name=_("Codigo"),
    )
    recipe = models.ForeignKey(
        "crafting.Recipe",
        on_delete=models.PROTECT,
        related_name="work_orders",
        verbose_name=_("Receita"),
    )
    output_ref = models.CharField(
        max_length=100,
        verbose_name=_("Produto"),
        help_text=_("Copiado da Recipe no plan"),
    )

    # The two numbers
    quantity = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        verbose_name=_("Quantidade Alvo"),
        help_text=_("Alvo atual (mutavel via adjust)"),
    )
    produced = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        null=True,
        blank=True,
        verbose_name=_("Produzido"),
        help_text=_("Set no close, imutavel depois"),
    )

    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name=_("Status"),
    )
    rev = models.PositiveIntegerField(
        default=0,
        verbose_name=_("Revisao"),
        help_text=_("Optimistic concurrency counter"),
    )

    scheduled_date = models.DateField(
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
        verbose_name=_("Finalizada em"),
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
        help_text=_("Ref da Position no Stocking (ex: 'producao')"),
    )
    assigned_ref = models.CharField(
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
        verbose_name = _("Ordem de Producao")
        verbose_name_plural = _("Ordens de Producao")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "scheduled_date"]),
            models.Index(fields=["output_ref", "status"]),
            models.Index(fields=["scheduled_date"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="craft_wo_quantity_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} - {self.recipe.name}" if self.code else f"WO-{self.pk}"

    def clean(self):
        super().clean()
        if self.quantity is not None and self.quantity <= 0:
            raise ValidationError({"quantity": _("Deve ser maior que zero.")})

    def save(self, *args, **kwargs):
        """Auto-generate code via CodeSequence if blank."""
        if not self.code:
            self.code = self._generate_code()
        # full_clean only on creation/full save — services use
        # save(update_fields=[...]) and validate in the service layer.
        if not kwargs.get("update_fields"):
            self.full_clean()
        super().save(*args, **kwargs)

    def _generate_code(self) -> str:
        """Generate unique code: WO-YYYY-NNNNN."""
        from shopman.crafting.models.sequence import CodeSequence

        year = timezone.now().year
        prefix = f"WO-{year}"
        next_num = CodeSequence.next_value(prefix)
        return f"{prefix}-{next_num:05d}"

    # ── Properties ──────────────────────────────────────────────

    @property
    def loss(self) -> Decimal | None:
        """Quantity lost: target - produced."""
        if self.produced is None:
            return None
        return max(self.quantity - self.produced, Decimal("0"))

    @property
    def yield_rate(self) -> Decimal | None:
        """Efficiency: produced / quantity."""
        if self.produced is None or not self.quantity:
            return None
        return self.produced / self.quantity
