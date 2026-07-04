"""Operator order mutation facade.

Backstage views use this module for order mutations. Projections may still read
orders directly, but mutation paths should not decide lifecycle transitions in
the HTTP layer.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Order

from shopman.shop.services.cancellation import cancel
from shopman.shop.services.order_helpers import get_fulfillment_type

logger = logging.getLogger(__name__)

_NEXT_STATUS_MAP: dict[str, str] = {
    Order.Status.CONFIRMED: Order.Status.PREPARING,
    Order.Status.PREPARING: Order.Status.READY,
    Order.Status.READY: Order.Status.COMPLETED,
    Order.Status.DISPATCHED: Order.Status.DELIVERED,
    Order.Status.DELIVERED: Order.Status.COMPLETED,
}


def find_order(ref: str) -> Order | None:
    """Return an order by public reference, if it exists."""
    return Order.objects.filter(ref=ref).first()


def recent_history(*, limit: int = 20) -> list[Order]:
    """Return recent closed orders for the operator history view."""
    return list(
        Order.objects.filter(
            status__in=(
                Order.Status.COMPLETED,
                Order.Status.DELIVERED,
                Order.Status.CANCELLED,
            )
        )
        .prefetch_related("items")
        .order_by("-updated_at")[:limit]
    )


def confirm_order(order: Order, *, actor: str) -> None:
    """Confirm a manually accepted order."""
    if order.status != Order.Status.NEW:
        raise ValueError("Pedido não está aguardando confirmação")

    from shopman.shop.lifecycle import ensure_confirmable, ensure_payment_captured

    ensure_payment_captured(order)
    ensure_confirmable(order)
    order.transition_status(Order.Status.CONFIRMED, actor=actor)


def reject_order(
    order: Order,
    *,
    reason: str,
    actor: str,
    rejected_by: str,
    cancellation_code: str = "",
) -> None:
    """Reject an order and queue the customer notification directive.

    ``cancellation_code`` is the marketplace (iFood) cancellation code the
    operator picked; it rides ``order.data`` to the status-callback handler.
    """
    if order.status != Order.Status.NEW:
        raise ValueError("Pedido só pode ser rejeitado enquanto aguarda confirmação")

    extra_data = {"rejected_by": rejected_by}
    if cancellation_code:
        extra_data["ifood_cancellation_code"] = cancellation_code
    cancel(
        order,
        reason=reason,
        actor=actor,
        extra_data=extra_data,
    )
    from shopman.shop.services import notification

    notification.send(order, "order_rejected", reason=reason, rejected_by=rejected_by)
    logger.info("operator_reject order=%s reason=%s", order.ref, reason)


def next_status_for(order: Order) -> str:
    """Return the canonical next operator-driven status, or empty string."""
    if order.status == Order.Status.READY and get_fulfillment_type(order) == "delivery":
        return Order.Status.DISPATCHED
    return _NEXT_STATUS_MAP.get(order.status, "")


def advance_block_reason(order: Order) -> str:
    """Why advancing is blocked right now, or '' if ``advance_order`` would run.

    Single source for the operator-advance gate: ``advance_order`` raises with
    this reason, and the operator queue reads it to decide whether to offer the
    advance action — so the prediction always matches the enforcement.
    """
    if not next_status_for(order):
        return "Pedido não possui próxima etapa"
    if order.status == Order.Status.CONFIRMED and _requires_captured_payment_for_work(order):
        return "Pagamento ainda não foi confirmado. Aguarde antes de iniciar o preparo."
    return ""


def advance_order(order: Order, *, actor: str) -> str:
    """Advance an order through the operator lifecycle."""
    blocked = advance_block_reason(order)
    if blocked:
        raise ValueError(blocked)
    next_status = next_status_for(order)
    _sync_delivery_fulfillment(order, next_status)
    order.transition_status(next_status, actor=actor)
    if next_status == Order.Status.DISPATCHED and get_fulfillment_type(order) == "delivery":
        schedule_delivery_auto_complete(order)
    return next_status


def schedule_delivery_auto_complete(order: Order) -> None:
    """Agenda a auto-conclusão de um pedido em entrega: ETA + folga após a saída.

    Rede de segurança para o trecho sem rastreio — se nem o cliente ("Recebi")
    nem o operador ("Marcar entregue") fecharem, o pedido não fica preso em
    "saiu para entrega". Idempotente (reusa o directive enfileirado); respeita o
    desligamento (folga <= 0). O handler revalida o status, então um pedido já
    fechado quando o directive vence é um no-op.
    """
    from datetime import timedelta

    from django.utils import timezone
    from shopman.orderman.models import Directive

    from shopman.shop.directives import DELIVERY_AUTO_COMPLETE
    from shopman.shop.models import Shop
    from shopman.shop.services.order_helpers import (
        delivery_auto_complete_grace_minutes,
        delivery_eta_minutes,
    )

    shop = Shop.load()
    grace = delivery_auto_complete_grace_minutes(shop)
    if grace <= 0:
        return  # auto-conclusão desligada via config
    minutes = delivery_eta_minutes(shop, order.data or {}) + grace
    available_at = timezone.now() + timedelta(minutes=minutes)

    existing = (
        Directive.objects.filter(
            topic=DELIVERY_AUTO_COMPLETE,
            payload__order_ref=order.ref,
            status=Directive.Status.QUEUED,
        )
        .order_by("available_at", "id")
        .first()
    )
    if existing:
        existing.available_at = available_at
        existing.save(update_fields=["available_at", "updated_at"])
        return
    Directive.objects.create(
        topic=DELIVERY_AUTO_COMPLETE,
        payload={"order_ref": order.ref},
        available_at=available_at,
    )


def confirm_received(order: Order, *, actor: str = "customer") -> bool:
    """Customer confirms a dispatched delivery arrived → mark delivered.

    Same machinery as the operator "Marcar como Entregue" (fulfillment sync +
    transition), so handlers/notifications fire exactly once. Only valid while
    the order is out for delivery; idempotent (returns False) otherwise — couriers
    são terceirizados, então o cliente fechando o loop é uma das vias legítimas
    para o pedido virar "entregue" (junto do operador e da auto-conclusão).
    """
    if order.status != Order.Status.DISPATCHED or get_fulfillment_type(order) != "delivery":
        return False
    _sync_delivery_fulfillment(order, Order.Status.DELIVERED)
    order.transition_status(Order.Status.DELIVERED, actor=actor)
    return True


def cancel_order(
    order: Order,
    *,
    reason: str,
    actor: str,
    cancellation_code: str = "",
    customer_note: str = "",
) -> None:
    """Cancel an order through the canonical cancellation service.

    ``cancellation_code`` (iFood) rides ``order.data`` to the status-callback handler.

    ``customer_note`` is the operator-authored, customer-facing justification. It is
    stored under ``order.data["cancellation_note"]`` and surfaced to the customer in
    the ``order_cancelled`` notification. Kept separate from ``cancellation_reason``,
    which also carries machine codes (``pix_timeout``, ``customer_requested``) that
    must never reach the customer. Empty when the operator gave no reason → the
    customer gets the plain cancellation message.
    """
    extra_data: dict[str, str] = {}
    if cancellation_code:
        extra_data["ifood_cancellation_code"] = cancellation_code
    if customer_note.strip():
        extra_data["cancellation_note"] = customer_note.strip()
    cancel(order, reason=reason, actor=actor, extra_data=extra_data or None)


def settle_delivery_cash(order: Order, *, cash_shift, actor: str, amount_q: int | None = None) -> int:
    """Record cash returned from a delivery order into the active CashShift."""
    if get_fulfillment_type(order) != "delivery":
        raise ValueError("Acerto de entrega só se aplica a pedidos delivery.")
    if order.status not in {Order.Status.DISPATCHED, Order.Status.DELIVERED, Order.Status.COMPLETED}:
        raise ValueError("Acerto de entrega só é permitido depois da saída para entrega.")
    if cash_shift is None or getattr(cash_shift, "status", "") != "open":
        raise ValueError("Abra um turno de caixa para registrar o acerto.")

    data = dict(order.data or {})
    payment = dict(data.get("payment") or {})
    if payment.get("collection") != "on_delivery" or payment.get("method") != "cash":
        raise ValueError("Pedido não está marcado como dinheiro na entrega.")
    if payment.get("cod_settled_at"):
        raise ValueError("Dinheiro da entrega já foi acertado.")

    amount = int(amount_q if amount_q is not None else order.total_q or 0)
    if amount <= 0:
        raise ValueError("Valor de acerto inválido.")
    if amount != int(order.total_q or 0):
        raise ValueError("Valor de acerto deve bater com o total do pedido.")

    tenders = list(payment.get("tenders") or [])
    updated = False
    for tender in tenders:
        if tender.get("method") == "cash" and tender.get("collection") == "on_delivery":
            tender["collection"] = "terminal"
            tender["status"] = "received"
            tender["cash_shift_id"] = cash_shift.pk
            tender["terminal_ref"] = cash_shift.terminal.ref
            tender["received_at"] = timezone_now_iso()
            updated = True
            break
    if not updated:
        tenders.append({
            "method": "cash",
            "amount_q": amount,
            "collection": "terminal",
            "status": "received",
            "cash_shift_id": cash_shift.pk,
            "terminal_ref": cash_shift.terminal.ref,
            "received_at": timezone_now_iso(),
        })

    payment["tenders"] = tenders
    payment["cash_received_q"] = amount
    payment["cod_cash_shift_id"] = cash_shift.pk
    payment["cod_terminal_ref"] = cash_shift.terminal.ref
    payment["cod_settled_at"] = timezone_now_iso()
    payment["cod_settled_by"] = actor
    data["payment"] = payment
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    order.emit_event(
        event_type="payment_collected",
        actor=actor,
        payload={
            "method": "cash",
            "amount_q": amount,
            "cash_shift_id": cash_shift.pk,
            "terminal_ref": cash_shift.terminal.ref,
        },
    )
    logger.info("operator_settle_delivery_cash order=%s shift=%s amount=%s", order.ref, cash_shift.pk, amount)
    return amount


def save_internal_notes(order: Order, *, notes: str) -> None:
    """Persist operator-only notes on the order data payload."""
    data = dict(order.data or {})
    data["internal_notes"] = notes
    order.data = data
    order.save(update_fields=["data", "updated_at"])


def assign_order(order: Order, *, operator_id: int, operator_name: str, actor: str) -> None:
    """Claim an order for an operator ("estou atendendo"), stored in Order.data.

    Contextual, not structural → lives in the JSONField (no migration), per the
    Core extensibility contract. Idempotent: re-claiming refreshes the holder.
    """
    from django.utils import timezone

    data = dict(order.data or {})
    data["assignment"] = {
        "operator_id": operator_id,
        "operator_name": operator_name,
        "at": timezone.now().isoformat(),
    }
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    order.emit_event(
        event_type="order_assigned",
        actor=actor,
        payload={"operator_id": operator_id, "operator_name": operator_name},
    )


def unassign_order(order: Order, *, actor: str) -> None:
    """Release an order's operator claim. No-op if it was not claimed."""
    data = dict(order.data or {})
    if data.pop("assignment", None) is None:
        return
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    order.emit_event(event_type="order_unassigned", actor=actor)


def add_comment(order: Order, *, note: str, actor: str) -> None:
    """Append a timestamped operator comment to the order timeline (OrderEvent).

    Distinct from ``internal_notes`` (a single editable blob): a comment is an
    immutable, attributed entry that shows up in the timeline like any other
    event — useful for a running operator log/handover.
    """
    text = (note or "").strip()
    if not text:
        raise ValueError("Comentário vazio")
    order.emit_event(event_type="operator_comment", actor=actor, payload={"note": text})


def _requires_captured_payment_for_work(order: Order) -> bool:
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return False
    from shopman.shop.services import payment as payment_service

    return payment_service.has_sufficient_captured_payment(order) is not True


def timezone_now_iso() -> str:
    from django.utils import timezone

    return timezone.now().isoformat()


def _sync_delivery_fulfillment(order: Order, next_status: str) -> None:
    """Keep the delivery fulfillment lifecycle aligned with operator actions."""
    if get_fulfillment_type(order) != "delivery":
        return
    if next_status not in {Order.Status.DISPATCHED, Order.Status.DELIVERED}:
        return

    from shopman.orderman.models import Fulfillment

    from shopman.shop.services import fulfillment as fulfillment_service

    fulfillment = order.fulfillments.order_by("pk").first()
    if fulfillment is None:
        fulfillment = fulfillment_service.create(order) or order.fulfillments.order_by("pk").first()
    if fulfillment is None:
        return

    if next_status == Order.Status.DISPATCHED:
        _advance_fulfillment_to(
            fulfillment,
            Fulfillment.Status.DISPATCHED,
            fulfillment_service,
        )
    elif next_status == Order.Status.DELIVERED:
        _advance_fulfillment_to(
            fulfillment,
            Fulfillment.Status.DELIVERED,
            fulfillment_service,
        )


def _advance_fulfillment_to(fulfillment, target_status: str, fulfillment_service) -> None:
    from shopman.orderman.models import Fulfillment

    if fulfillment.status == target_status:
        return
    if fulfillment.status == Fulfillment.Status.DELIVERED:
        return

    if target_status == Fulfillment.Status.DISPATCHED:
        if fulfillment.status == Fulfillment.Status.PENDING:
            fulfillment_service.update(fulfillment, Fulfillment.Status.IN_PROGRESS)
            fulfillment.refresh_from_db()
        if fulfillment.status == Fulfillment.Status.IN_PROGRESS:
            fulfillment_service.update(fulfillment, Fulfillment.Status.DISPATCHED)
        return

    if target_status == Fulfillment.Status.DELIVERED:
        if fulfillment.status in {Fulfillment.Status.PENDING, Fulfillment.Status.IN_PROGRESS}:
            _advance_fulfillment_to(
                fulfillment,
                Fulfillment.Status.DISPATCHED,
                fulfillment_service,
            )
            fulfillment.refresh_from_db()
        if fulfillment.status == Fulfillment.Status.DISPATCHED:
            fulfillment_service.update(fulfillment, Fulfillment.Status.DELIVERED)
