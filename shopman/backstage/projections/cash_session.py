"""CashSessionReportProjection — leitura X/Z e histórico de turnos do dia.

Read model da antesala do PDV (ADMIN-ROLE-PLAN WP-ADM-4, benchmark Odoo POS):

- **Leitura X** — parcial do turno ABERTO do operador: abertura, movimentos
  (sangria/suprimento/ajuste), contagem de vendas e vendas por método.
- **Leitura Z** — fechamento de cada turno FECHADO do dia: abertura, valor
  CONTADO (contagem cega), movimentos e totais operacionais de vendas.
- **Histórico do dia** — totais agregados de turnos e vendas.

⚠️ BLIND COUNT (anti-fraude): o PDV NUNCA expõe o valor ESPERADO da gaveta —
nem no X (turno aberto), nem no Z (turno fechado). A conferência (esperado vs
contado vs variância — ``expected_amount_q`` / ``difference_q``) é da
retaguarda (Admin/Unfold, ``audit_cashshift``). Aqui, o Z mostra o que o
operador CONTOU e o que a operação registrou, nada derivável do esperado.

A atribuição de vendas a um turno espelha ``CashShift.close()`` (read-only,
sem adoção de órfãs): tag durável ``Order.data.pos.cash_shift_id`` /
``payment.cod_cash_shift_id`` / tender ``cash_shift_id`` decide; sem tag, vale
a janela temporal do turno no canal do terminal.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import models
from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.backstage.models import CashShift
from shopman.backstage.presentation.status import payment_method_label

logger = logging.getLogger(__name__)

_METHOD_ORDER = ("cash", "pix", "card", "external")


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CashMovementRowProjection:
    """A manual drawer movement inside a shift."""

    kind: str  # "sangria" | "suprimento" | "ajuste"
    kind_label: str  # "Sangria" | "Suprimento" | "Ajuste"
    amount_q: int  # signed for ajuste (negative = falta)
    amount_display: str
    reason: str
    created_by: str
    created_at: str  # ISO datetime


@dataclass(frozen=True)
class SalesByMethodRowProjection:
    """Sales received by one payment method within a shift."""

    method: str  # "cash" | "pix" | "card" | "external"
    method_label: str
    orders_count: int
    amount_q: int
    amount_display: str


@dataclass(frozen=True)
class ShiftReadingProjection:
    """One shift's operational reading (X when open, Z when closed).

    BLIND: never carries the expected drawer amount nor the variance — the
    reconciliation lives in the backoffice, not at the terminal.
    """

    shift_id: int
    status: str  # "open" | "closed"
    terminal_ref: str
    terminal_label: str
    operator: str
    opened_at: str  # ISO datetime
    closed_at: str  # ISO datetime, "" while open
    opening_amount_q: int
    opening_amount_display: str
    counted_amount_q: int | None  # blind count; None while open
    counted_amount_display: str  # "" while open
    movements: tuple[CashMovementRowProjection, ...]
    movements_in_q: int  # suprimentos + ajustes positivos
    movements_in_display: str
    movements_out_q: int  # sangrias + ajustes negativos (valor absoluto)
    movements_out_display: str
    sales_count: int
    sales_total_q: int
    sales_total_display: str
    sales_by_method: tuple[SalesByMethodRowProjection, ...]
    notes: str  # "" while open


@dataclass(frozen=True)
class DayTotalsProjection:
    """Aggregated shift/sales history for the day (closed shifts)."""

    shifts_count: int
    sales_count: int
    sales_total_q: int
    sales_total_display: str
    counted_total_q: int
    counted_total_display: str
    sales_by_method: tuple[SalesByMethodRowProjection, ...]


@dataclass(frozen=True)
class CashSessionReportProjection:
    """Top-level read model for the session report page (/session/report)."""

    date: str  # ISO date
    date_display: str  # "17/07/2026"
    x_reading: ShiftReadingProjection | None  # operator's OPEN shift, or None
    has_open_shift: bool
    z_readings: tuple[ShiftReadingProjection, ...]  # today's CLOSED shifts
    has_closed_shifts: bool
    day_totals: DayTotalsProjection


# ── Builder ────────────────────────────────────────────────────────────


def build_cash_session_report(*, operator) -> CashSessionReportProjection:
    """Build the X/Z report for today, scoped to the requesting operator's X.

    The X reading belongs to the operator asking (their open shift); the Z list
    covers every shift closed today, terminal-wide — the shift history the
    antesala shows. Neither exposes expected/variance (blind count).
    """
    today = timezone.localdate()

    open_shift = CashShift.get_open_for_operator(operator)
    x_reading = _shift_reading(open_shift) if open_shift else None

    closed = (
        CashShift.objects.filter(status=CashShift.Status.CLOSED, closed_at__date=today)
        .select_related("terminal", "operator")
        .order_by("closed_at")
    )
    z_readings = tuple(_shift_reading(shift) for shift in closed)

    return CashSessionReportProjection(
        date=today.isoformat(),
        date_display=today.strftime("%d/%m/%Y"),
        x_reading=x_reading,
        has_open_shift=x_reading is not None,
        z_readings=z_readings,
        has_closed_shifts=bool(z_readings),
        day_totals=_day_totals(z_readings),
    )


# ── Internals ──────────────────────────────────────────────────────────


def _shift_reading(shift: CashShift) -> ShiftReadingProjection:
    movements = tuple(
        CashMovementRowProjection(
            kind=movement.movement_type,
            kind_label=movement.get_movement_type_display(),
            amount_q=movement.amount_q,
            amount_display=format_money(movement.amount_q),
            reason=movement.reason,
            created_by=movement.created_by,
            created_at=movement.created_at.isoformat() if movement.created_at else "",
        )
        for movement in shift.movements.order_by("created_at")
    )
    movements_in_q = sum(row.amount_q for row in movements if _is_inflow(row))
    movements_out_q = sum(abs(row.amount_q) for row in movements if not _is_inflow(row))

    sales_count, sales_total_q, by_method = _shift_sales(shift)
    is_open = shift.status == CashShift.Status.OPEN

    return ShiftReadingProjection(
        shift_id=shift.pk,
        status="open" if is_open else "closed",
        terminal_ref=shift.terminal.ref,
        terminal_label=shift.terminal.label or shift.terminal.ref,
        operator=shift.operator.get_username(),
        opened_at=shift.opened_at.isoformat() if shift.opened_at else "",
        closed_at=shift.closed_at.isoformat() if shift.closed_at else "",
        opening_amount_q=shift.opening_amount_q or 0,
        opening_amount_display=format_money(shift.opening_amount_q or 0),
        counted_amount_q=None if is_open else (shift.blind_closing_amount_q or 0),
        counted_amount_display="" if is_open else format_money(shift.blind_closing_amount_q or 0),
        movements=movements,
        movements_in_q=movements_in_q,
        movements_in_display=format_money(movements_in_q),
        movements_out_q=movements_out_q,
        movements_out_display=format_money(movements_out_q),
        sales_count=sales_count,
        sales_total_q=sales_total_q,
        sales_total_display=format_money(sales_total_q),
        sales_by_method=_method_rows(by_method),
        notes=shift.notes or "",
    )


def _is_inflow(row: CashMovementRowProjection) -> bool:
    if row.kind == "suprimento":
        return True
    if row.kind == "ajuste":
        return row.amount_q >= 0
    return False  # sangria


def _shift_sales(shift: CashShift) -> tuple[int, int, dict[str, dict]]:
    """Count the shift's sales and split received amounts by method (read-only).

    Mirrors the attribution of ``CashShift.close()`` without mutating orders:
    an order belongs to the shift when its durable tag says so, or when it is
    untagged and was created inside the shift's window on the terminal's
    channel. Cash follows the COLLECTION tags (COD ``cod_cash_shift_id`` and
    tender ``cash_shift_id`` name who received the money); other methods follow
    the creating shift.
    """
    from django.conf import settings
    from shopman.orderman.models import Order

    channel_ref = shift.terminal.channel_ref or getattr(settings, "SHOPMAN_POS_CHANNEL_REF", "pdv")
    window_end = shift.closed_at or timezone.now()

    orders_qs = (
        Order.objects.filter(channel_ref=channel_ref)
        .filter(
            models.Q(data__pos__cash_shift_id=shift.pk)
            | models.Q(data__payment__cod_cash_shift_id=shift.pk)
            | models.Q(created_at__gte=shift.opened_at, created_at__lte=window_end)
        )
        .exclude(status="cancelled")
    )

    sales_count = 0
    sales_total_q = 0
    by_method: dict[str, dict] = {}

    for order in orders_qs:
        data = order.data or {}
        payment = data.get("payment") or {}
        pos_shift_id = _int_or_none((data.get("pos") or {}).get("cash_shift_id"))
        in_window = bool(
            order.created_at and shift.opened_at <= order.created_at <= window_end
        )
        belongs = pos_shift_id == shift.pk or (pos_shift_id is None and in_window)

        if belongs:
            sales_count += 1
            sales_total_q += int(order.total_q or 0)

        cash_received_q = payment.get("cash_received_q")
        if cash_received_q is not None:
            cod_shift_id = _int_or_none(payment.get("cod_cash_shift_id"))
            if cod_shift_id:
                # COD: o dinheiro é do turno que COLETOU, não do que criou.
                if cod_shift_id == shift.pk:
                    _tally(by_method, "cash", int(cash_received_q or 0))
                continue
            if belongs:
                _tally(by_method, "cash", int(cash_received_q or 0))
            continue

        tenders = payment.get("tenders") or []
        if tenders:
            for tender in tenders:
                method = str(tender.get("method") or "").strip().lower()
                amount_q = _int_or_none(tender.get("amount_q")) or 0
                if not method or amount_q <= 0:
                    continue
                if method == "cash":
                    if tender.get("collection", "terminal") != "terminal":
                        continue  # COD pendente vive no braço cash_received_q
                    tender_shift_id = _int_or_none(tender.get("cash_shift_id"))
                    if tender_shift_id:
                        if tender_shift_id != shift.pk:
                            continue
                    elif not belongs:
                        continue
                    _tally(by_method, "cash", amount_q)
                elif belongs:
                    _tally(by_method, method, amount_q)
            continue

        method = str(payment.get("method") or "").strip().lower()
        if not belongs or not method or method == "mixed":
            continue
        if method == "cash" and payment.get("collection", "terminal") == "on_delivery":
            continue
        _tally(by_method, method, int(order.total_q or 0))

    return sales_count, sales_total_q, by_method


def _tally(by_method: dict[str, dict], method: str, amount_q: int) -> None:
    bucket = by_method.setdefault(method, {"orders_count": 0, "amount_q": 0})
    bucket["orders_count"] += 1
    bucket["amount_q"] += amount_q


def _method_rows(by_method: dict[str, dict]) -> tuple[SalesByMethodRowProjection, ...]:
    ordered = sorted(
        by_method.items(),
        key=lambda pair: (
            _METHOD_ORDER.index(pair[0]) if pair[0] in _METHOD_ORDER else len(_METHOD_ORDER),
            pair[0],
        ),
    )
    return tuple(
        SalesByMethodRowProjection(
            method=method,
            method_label=payment_method_label(method),
            orders_count=int(bucket["orders_count"]),
            amount_q=int(bucket["amount_q"]),
            amount_display=format_money(int(bucket["amount_q"])),
        )
        for method, bucket in ordered
    )


def _day_totals(z_readings: tuple[ShiftReadingProjection, ...]) -> DayTotalsProjection:
    sales_total_q = sum(reading.sales_total_q for reading in z_readings)
    counted_total_q = sum(reading.counted_amount_q or 0 for reading in z_readings)

    merged: dict[str, dict] = {}
    for reading in z_readings:
        for row in reading.sales_by_method:
            bucket = merged.setdefault(row.method, {"orders_count": 0, "amount_q": 0})
            bucket["orders_count"] += row.orders_count
            bucket["amount_q"] += row.amount_q

    return DayTotalsProjection(
        shifts_count=len(z_readings),
        sales_count=sum(reading.sales_count for reading in z_readings),
        sales_total_q=sales_total_q,
        sales_total_display=format_money(sales_total_q),
        counted_total_q=counted_total_q,
        counted_total_display=format_money(counted_total_q),
        sales_by_method=_method_rows(merged),
    )


def _int_or_none(value) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
