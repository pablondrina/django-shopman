"""POS command service for backstage cash-register mutations."""

from __future__ import annotations

from shopman.backstage.services.exceptions import POSError


def parse_money_to_q(raw) -> int:
    try:
        normalized = str(raw or "0").strip().replace(",", ".")
        return round(float(normalized) * 100)
    except (TypeError, ValueError):
        return 0


def open_cash_session(*, operator, opening_amount_raw="0"):
    from shopman.backstage.models import CashRegisterSession

    existing = CashRegisterSession.get_open_for_operator(operator)
    if existing:
        return existing

    opening_amount_q = max(0, parse_money_to_q(opening_amount_raw))
    return CashRegisterSession.objects.create(
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
    from shopman.backstage.models import CashMovement, CashRegisterSession

    session = CashRegisterSession.get_open_for_operator(operator)
    if not session:
        raise POSError("Caixa não aberto.")

    normalized_type = movement_type if movement_type in {"sangria", "suprimento", "ajuste"} else "sangria"
    amount_q = parse_money_to_q(amount_raw)
    if amount_q <= 0:
        raise POSError("Valor inválido.")

    return CashMovement.objects.create(
        session=session,
        movement_type=normalized_type,
        amount_q=amount_q,
        reason=reason.strip(),
        created_by=operator.username,
    )


def close_cash_session(*, operator, closing_amount_raw="0", notes: str = ""):
    from shopman.backstage.models import CashRegisterSession

    session = CashRegisterSession.get_open_for_operator(operator)
    if not session:
        raise POSError("Caixa não aberto.")

    session.close(
        closing_amount_q=parse_money_to_q(closing_amount_raw),
        notes=notes.strip(),
    )
    return session
