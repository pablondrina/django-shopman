"""POS mutation service for backstage cash-shift mutations."""

from __future__ import annotations

from shopman.backstage.services.exceptions import POSError


def parse_money_to_q(raw) -> int:
    try:
        normalized = str(raw or "0").strip().replace(",", ".")
        return round(float(normalized) * 100)
    except (TypeError, ValueError):
        return 0


def open_cash_shift(*, operator, opening_amount_raw="0", terminal_ref: str = ""):
    from shopman.backstage.models import CashShift

    existing = CashShift.get_open_for_operator(operator)
    if existing:
        return existing

    terminal = _terminal(terminal_ref)
    terminal_open = CashShift.get_open_for_terminal(terminal)
    if terminal_open:
        raise POSError("Terminal POS já possui turno aberto.")

    opening_amount_q = max(0, parse_money_to_q(opening_amount_raw))
    return CashShift.objects.create(
        terminal=terminal,
        operator=operator,
        opening_amount_q=opening_amount_q,
    )


def register_cash_movement(
    *,
    operator,
    movement_type: str = "sangria",
    amount_raw="0",
    reason: str = "",
):
    from shopman.backstage.models import CashMovement, CashShift

    shift = CashShift.get_open_for_operator(operator)
    if not shift:
        raise POSError("Caixa não aberto.")
    if shift.status != CashShift.Status.OPEN:
        raise POSError("Turno de caixa já fechado.")

    normalized_type = movement_type if movement_type in {"sangria", "suprimento", "ajuste"} else "sangria"
    amount_q = parse_money_to_q(amount_raw)
    if amount_q <= 0:
        raise POSError("Valor inválido.")

    return CashMovement.objects.create(
        shift=shift,
        movement_type=normalized_type,
        amount_q=amount_q,
        reason=reason.strip(),
        created_by=operator.username,
    )


def close_cash_shift(*, operator, closing_amount_raw="0", notes: str = ""):
    from shopman.backstage.models import CashShift

    shift = CashShift.get_open_for_operator(operator)
    if not shift:
        raise POSError("Caixa não aberto.")

    shift.close(
        blind_closing_amount_q=parse_money_to_q(closing_amount_raw),
        notes=notes.strip(),
    )
    return shift


def _terminal(terminal_ref: str = ""):
    from shopman.backstage.models import POSTerminal

    ref = str(terminal_ref or "").strip()
    if ref:
        terminal = POSTerminal.objects.filter(ref=ref, is_active=True).first()
        if not terminal:
            raise POSError("Terminal POS inválido.")
        return terminal
    terminal = POSTerminal.objects.filter(is_active=True).order_by("ref").first()
    return terminal or POSTerminal.default()
