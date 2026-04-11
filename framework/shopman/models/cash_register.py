"""Cash register models — CashRegisterSession + CashMovement."""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class CashRegisterSession(models.Model):
    """
    Represents a single cash register shift opened and closed by an operator.

    Lifecycle: open → closed.
    Only one session per operator can be open at a time.
    """

    class Status(models.TextChoices):
        OPEN = "open", "Aberto"
        CLOSED = "closed", "Fechado"

    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cash_sessions",
        verbose_name="Operador",
    )
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_amount_q = models.IntegerField(
        default=0,
        help_text="Valor de abertura em centavos (fundo de troco).",
    )
    closing_amount_q = models.IntegerField(
        null=True, blank=True,
        help_text="Valor informado no fechamento em centavos.",
    )
    expected_amount_q = models.IntegerField(
        null=True, blank=True,
        help_text="Calculado: abertura + vendas_dinheiro + suprimentos - sangrias.",
    )
    difference_q = models.IntegerField(
        null=True, blank=True,
        help_text="Diferença: fechamento informado - esperado (positivo = sobra).",
    )
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering = ["-opened_at"]
        verbose_name = "Sessão de Caixa"
        verbose_name_plural = "Sessões de Caixa"

    def __str__(self) -> str:
        return f"Caixa {self.operator.username} — {self.opened_at:%d/%m/%Y %H:%M} [{self.status}]"

    @classmethod
    def get_open_for_operator(cls, operator) -> CashRegisterSession | None:
        return cls.objects.filter(operator=operator, status=cls.Status.OPEN).first()

    def close(self, *, closing_amount_q: int, notes: str = "") -> None:
        """Close the session and compute expected_amount_q / difference_q."""
        from django.db.models import Sum

        from shopman.orderman.models import Order

        # Cash sales during this session
        cash_sales_q = (
            Order.objects.filter(
                channel_ref="balcao",
                created_at__gte=self.opened_at,
                created_at__lte=timezone.now(),
            )
            .exclude(status="cancelled")
            .filter(data__payment__method="cash")
            .aggregate(t=Sum("total_q"))["t"]
        ) or 0

        # Cash movements
        movements = self.movements.aggregate(
            suprimentos=Sum("amount_q", filter=models.Q(movement_type="suprimento")),
            sangrias=Sum("amount_q", filter=models.Q(movement_type="sangria")),
        )
        suprimentos_q = movements["suprimentos"] or 0
        sangrias_q = movements["sangrias"] or 0

        expected = self.opening_amount_q + cash_sales_q + suprimentos_q - sangrias_q

        self.closing_amount_q = closing_amount_q
        self.expected_amount_q = expected
        self.difference_q = closing_amount_q - expected
        self.notes = notes
        self.closed_at = timezone.now()
        self.status = self.Status.CLOSED
        self.save(update_fields=[
            "closing_amount_q", "expected_amount_q", "difference_q",
            "notes", "closed_at", "status",
        ])


class CashMovement(models.Model):
    """A single cash movement within a register session (sangria, suprimento, ajuste)."""

    class MovementType(models.TextChoices):
        SANGRIA = "sangria", "Sangria"
        SUPRIMENTO = "suprimento", "Suprimento"
        AJUSTE = "ajuste", "Ajuste"

    session = models.ForeignKey(
        CashRegisterSession,
        on_delete=models.CASCADE,
        related_name="movements",
        verbose_name="Sessão",
    )
    movement_type = models.CharField(
        max_length=20,
        choices=MovementType.choices,
        verbose_name="Tipo",
    )
    amount_q = models.IntegerField(help_text="Valor em centavos (sempre positivo).")
    reason = models.CharField(max_length=200, blank=True, default="")
    created_by = models.CharField(max_length=150, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Movimentação de Caixa"
        verbose_name_plural = "Movimentações de Caixa"

    def __str__(self) -> str:
        from shopman.utils.monetary import format_money
        return f"{self.get_movement_type_display()} R$ {format_money(self.amount_q)} — {self.session}"
