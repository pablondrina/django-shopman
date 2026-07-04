"""POS mutation service for backstage cash-shift mutations."""

from __future__ import annotations

from shopman.backstage.services.exceptions import POSError, POSPermissionError


def parse_money_to_q(raw) -> int:
    """Converte entrada do operador ("120", "120,50", "-10") em centavos.

    Entrada ilegível levanta POSError — devolver 0 silencioso num fechamento
    CEGO transformaria um typo ("12,,30") numa diferença gigante sem aviso.
    """
    from decimal import InvalidOperation

    from shopman.utils.monetary import brl_to_q

    text = str(raw or "").strip().replace("R$", "").replace(" ", "").replace(",", ".")
    if not text:
        return 0
    try:
        # brl_to_q usa ROUND_HALF_UP (não banker's rounding), consistente com
        # o resto do sistema.
        return brl_to_q(text)
    except InvalidOperation as exc:
        raise POSError("Valor inválido.") from exc


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
    # Ajuste aceita valor negativo (falta/quebra na conferência); sangria e
    # suprimento continuam estritamente positivos.
    if normalized_type == "ajuste":
        if amount_q == 0:
            raise POSError("Valor inválido.")
    elif amount_q <= 0:
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


def close_blocking_shift(*, actor_user, shift_id, closing_amount_raw="0", notes: str = ""):
    """Fechamento cego SUPERVISÓRIO do turno que bloqueia o terminal.

    Destrava o beco de UX: quando o terminal tem um turno aberto que não é do
    operador atual, ele fica preso sem poder vender. Aqui o GERENTE
    (``perform_closing``) ou o DONO do turno conta a gaveta e fecha o turno
    bloqueante — liberando o terminal. Operador comum não fecha o caixa de
    outro (anti-fraude) → POSPermissionError.
    """
    from shopman.backstage.models import CashShift
    from shopman.backstage.permissions import can_close_day

    shift = CashShift.objects.filter(pk=shift_id, status=CashShift.Status.OPEN).first()
    if not shift:
        raise POSError("Turno não encontrado ou já fechado.")

    is_owner = shift.operator_id == getattr(actor_user, "pk", None)
    if not (can_close_day(actor_user) or is_owner):
        raise POSPermissionError("Sem permissão para fechar o turno de outro operador.")

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
