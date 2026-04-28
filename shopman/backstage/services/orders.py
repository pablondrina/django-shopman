"""Backstage order command facade."""

from __future__ import annotations

from shopman.backstage.services.exceptions import OrderError
from shopman.shop.services import operator_orders


def find_order(ref: str):
    return operator_orders.find_order(ref)


def confirm_order(order, *, actor: str):
    return operator_orders.confirm_order(order, actor=actor)


def reject_order(order, *, reason: str, actor: str, rejected_by: str):
    if not reason.strip():
        raise OrderError("Motivo obrigatório")
    return operator_orders.reject_order(
        order,
        reason=reason.strip(),
        actor=actor,
        rejected_by=rejected_by,
    )


def advance_order(order, *, actor: str):
    try:
        return operator_orders.advance_order(order, actor=actor)
    except ValueError as exc:
        raise OrderError("Ação inválida") from exc


def mark_paid(order, *, actor: str, operator_username: str):
    return operator_orders.mark_paid(
        order,
        actor=actor,
        operator_username=operator_username,
    )


def save_internal_notes(order, *, notes: str):
    return operator_orders.save_internal_notes(order, notes=notes)


def recent_history(*, limit: int = 20):
    return operator_orders.recent_history(limit=limit)
