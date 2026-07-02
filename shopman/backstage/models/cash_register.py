"""POS cash domain: terminals, shifts, and manual cash movements."""

from __future__ import annotations

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

_POS_CHANNEL_REF: str = getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv")


class POSTerminal(models.Model):
    """Physical or digital POS terminal."""

    ref = models.SlugField("ref", max_length=80, unique=True)
    label = models.CharField("rotulo", max_length=120, blank=True, default="")
    channel_ref = models.CharField("canal", max_length=80, default=_POS_CHANNEL_REF)
    location_ref = models.CharField("local", max_length=120, blank=True, default="")
    is_active = models.BooleanField("ativo", default=True)
    metadata = models.JSONField("metadados", default=dict, blank=True)
    created_at = models.DateTimeField("criado em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizado em", auto_now=True)

    class Meta:
        ordering = ["ref"]
        verbose_name = "terminal POS"
        verbose_name_plural = "terminais POS"

    def __str__(self) -> str:
        return self.label or self.ref

    @classmethod
    def default(cls) -> POSTerminal:
        terminal, _ = cls.objects.get_or_create(
            ref="pdv-main",
            defaults={
                "label": "PDV principal",
                "channel_ref": _POS_CHANNEL_REF,
                "is_active": True,
            },
        )
        return terminal


class CashShift(models.Model):
    """A single POS cash shift opened by an operator at a terminal."""

    class Status(models.TextChoices):
        OPEN = "open", "Aberto"
        CLOSED = "closed", "Fechado"
        VOID = "void", "Cancelado"

    terminal = models.ForeignKey(
        POSTerminal,
        on_delete=models.PROTECT,
        related_name="cash_shifts",
        verbose_name="Terminal",
    )
    operator = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cash_shifts",
        verbose_name="Operador",
    )
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)
    opening_amount_q = models.IntegerField(
        default=0,
        help_text="Valor de abertura em centavos (fundo de troco).",
    )
    blind_closing_amount_q = models.IntegerField(
        null=True,
        blank=True,
        help_text="Valor contado no fechamento cego em centavos.",
    )
    expected_amount_q = models.IntegerField(
        null=True,
        blank=True,
        help_text="Calculado: abertura + vendas_dinheiro + suprimentos - sangrias.",
    )
    difference_q = models.IntegerField(
        null=True,
        blank=True,
        help_text="Diferenca: contado - esperado (positivo = sobra).",
    )
    notes = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-opened_at"]
        verbose_name = "Turno de Caixa"
        verbose_name_plural = "Turnos de Caixa"
        permissions = [
            ("operate_pos", "Pode operar o PDV (abrir/fechar caixa, sangria, balcão)"),
            ("audit_cashshift", "Pode auditar turnos de caixa"),
            ("adjust_cashshift", "Pode ajustar turnos de caixa"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["operator"],
                condition=models.Q(status="open"),
                name="backstage_cashshift_open_operator_uq",
            ),
            models.UniqueConstraint(
                fields=["terminal"],
                condition=models.Q(status="open"),
                name="backstage_cashshift_open_terminal_uq",
            ),
            models.CheckConstraint(
                condition=models.Q(opening_amount_q__gte=0),
                name="backstage_cashshift_opening_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(blind_closing_amount_q__isnull=True)
                | models.Q(blind_closing_amount_q__gte=0),
                name="backstage_cashshift_blind_close_nonnegative",
            ),
        ]

    def __str__(self) -> str:
        return f"Caixa {self.operator.username} - {self.opened_at:%d/%m/%Y %H:%M} [{self.status}]"

    def save(self, *args, **kwargs):
        if not self.terminal_id:
            self.terminal = POSTerminal.default()
        super().save(*args, **kwargs)

    @classmethod
    def get_open_for_operator(cls, operator) -> CashShift | None:
        return cls.objects.filter(operator=operator, status=cls.Status.OPEN).first()

    @classmethod
    def get_open_for_terminal(cls, terminal) -> CashShift | None:
        return cls.objects.filter(terminal=terminal, status=cls.Status.OPEN).first()

    @transaction.atomic
    def close(
        self,
        *,
        blind_closing_amount_q: int | None = None,
        notes: str = "",
    ) -> None:
        """Close the shift and compute expected_amount_q / difference_q.

        Atômico: a adoção de vendas órfãs (order.save por venda no laço) e a
        gravação do fechamento (expected/status) são tudo-ou-nada. Um crash no
        meio não pode deixar pedidos carimbados a um turno que nunca fechou.
        """
        from django.db.models import Sum
        from shopman.orderman.models import Order

        counted_q = int(blind_closing_amount_q or 0)
        now = timezone.now()

        channel_ref = self.terminal.channel_ref or _POS_CHANNEL_REF
        # O braço com tag explícita deste turno NÃO leva teto de created_at:
        # uma venda em voo no instante do fechamento pertence a este turno.
        orders_qs = Order.objects.filter(channel_ref=channel_ref).filter(
            models.Q(data__pos__cash_shift_id=self.pk)
            | models.Q(data__payment__cod_cash_shift_id=self.pk)
            | models.Q(created_at__gte=self.opened_at, created_at__lte=now)
        )

        cash_sales_q = 0
        for order in orders_qs.exclude(status="cancelled"):
            data = order.data or {}
            payment = (order.data or {}).get("payment") or {}
            pos_shift_id = _int_or_none((data.get("pos") or {}).get("cash_shift_id"))
            # Um dinheiro tagueado a OUTRO turno de criação (pos_shift_id) só é
            # pulado no ramo SEM tag específica de coleta. COD e tenders trazem
            # a tag de QUEM RECEBEU o dinheiro (cod_cash_shift_id / tender
            # cash_shift_id) — essa tag decide, independente de quem criou a
            # venda (senão o dinheiro coletado por B numa venda de A some).
            created_by_other_shift = bool(pos_shift_id and pos_shift_id != self.pk)

            cash_received_q = payment.get("cash_received_q")
            if cash_received_q is not None:
                cod_shift_id = _int_or_none(payment.get("cod_cash_shift_id"))
                if cod_shift_id:
                    # COD: conta o turno que COLETOU, não o que criou.
                    if cod_shift_id == self.pk:
                        cash_sales_q += int(cash_received_q or 0)
                    continue
                if created_by_other_shift:
                    continue
                cash_sales_q += int(cash_received_q or 0)
                self._adopt_orphan_sale(order, pos_shift_id)
                continue
            tenders = payment.get("tenders") or []
            if tenders:
                adopted = False
                for tender in tenders:
                    if tender.get("method") != "cash" or tender.get("collection", "terminal") != "terminal":
                        continue
                    tender_shift_id = _int_or_none(tender.get("cash_shift_id"))
                    if tender_shift_id:
                        # Tender com tag de coleta: só conta se for deste turno.
                        if tender_shift_id != self.pk:
                            continue
                    else:
                        # Tender sem tag pertence ao turno que criou a venda.
                        if created_by_other_shift or order.created_at < self.opened_at:
                            continue
                    cash_sales_q += int(tender.get("amount_q") or 0)
                    adopted = adopted or not tender_shift_id
                if adopted:
                    self._adopt_orphan_sale(order, pos_shift_id)
                continue
            if payment.get("method") == "cash" and payment.get("collection", "terminal") != "on_delivery":
                if created_by_other_shift:
                    continue
                cash_sales_q += int(order.total_q or 0)
                self._adopt_orphan_sale(order, pos_shift_id)

        movements = self.movements.aggregate(
            suprimentos=Sum("amount_q", filter=models.Q(movement_type="suprimento")),
            sangrias=Sum("amount_q", filter=models.Q(movement_type="sangria")),
            ajustes=Sum("amount_q", filter=models.Q(movement_type="ajuste")),
        )
        suprimentos_q = movements["suprimentos"] or 0
        sangrias_q = movements["sangrias"] or 0
        ajustes_q = movements["ajustes"] or 0

        expected = self.opening_amount_q + cash_sales_q + suprimentos_q + ajustes_q - sangrias_q

        self.blind_closing_amount_q = counted_q
        self.expected_amount_q = expected
        self.difference_q = counted_q - expected
        self.notes = notes
        self.closed_at = now
        self.status = self.Status.CLOSED
        self.save(update_fields=[
            "blind_closing_amount_q", "expected_amount_q", "difference_q",
            "notes", "closed_at", "status",
        ])

    def _adopt_orphan_sale(self, order, pos_shift_id) -> None:
        """Carimba a venda sem turno com este turno ao contá-la no fechamento.

        Sem a adoção, uma venda cash não-tagueada seria somada de novo pelo
        fechamento de OUTRO terminal aberto no mesmo canal.
        """
        if pos_shift_id == self.pk:
            return
        data = dict(order.data or {})
        pos_data = dict(data.get("pos") or {})
        pos_data["cash_shift_id"] = self.pk
        data["pos"] = pos_data
        order.data = data
        order.save(update_fields=["data", "updated_at"])


def _int_or_none(value) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


class CashMovement(models.Model):
    """A manual cash movement within a cash shift."""

    class MovementType(models.TextChoices):
        SANGRIA = "sangria", "Sangria"
        SUPRIMENTO = "suprimento", "Suprimento"
        AJUSTE = "ajuste", "Ajuste"

    shift = models.ForeignKey(
        CashShift,
        on_delete=models.CASCADE,
        related_name="movements",
        verbose_name="Turno",
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
        constraints = [
            # Ajuste registra sobra (+) ou falta (−) da conferência; sangria e
            # suprimento são estritamente positivos.
            models.CheckConstraint(
                condition=models.Q(amount_q__gt=0) | (
                    models.Q(movement_type="ajuste") & ~models.Q(amount_q=0)
                ),
                name="backstage_cashmovement_amount_positive",
            ),
        ]

    def __str__(self) -> str:
        from shopman.utils.monetary import format_money

        return f"{self.get_movement_type_display()} R$ {format_money(self.amount_q)} - {self.shift}"
