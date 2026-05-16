"""
Confirmation handler — resolve a NEW order after its confirmation timeout.

Fires once a ``confirmation.timeout`` directive reaches its ``expires_at``.
The terminal action is dictated by ``payload["action"]``:

- ``confirm`` → auto-confirm the order (auto_confirm mode).
- ``cancel``  → auto-cancel the order (auto_cancel mode).

If the operator has already moved the order out of ``NEW`` (by explicitly
confirming or cancelling within the window) the handler noops.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError, InvalidTransition
from shopman.orderman.models import Directive

from shopman.shop.directives import CONFIRMATION_TIMEOUT, ORDER_STALE_NEW_ALERT

logger = logging.getLogger(__name__)


class ConfirmationTimeoutHandler:
    """Resolve pedido após timeout de confirmação. Topic: confirmation.timeout"""

    topic = CONFIRMATION_TIMEOUT

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.lifecycle import ensure_confirmable

        payload = message.payload
        order_ref = payload["order_ref"]
        action = payload.get("action", "confirm")
        expires_at = datetime.fromisoformat(payload["expires_at"])

        if not timezone.is_aware(expires_at):
            expires_at = timezone.make_aware(expires_at)

        if timezone.now() < expires_at:
            # Defer: not yet expired, reschedule
            message.status = "queued"
            message.available_at = expires_at
            message.save(update_fields=["status", "available_at", "updated_at"])
            return

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            return

        if order.status != Order.Status.NEW:
            # Operator already resolved the order within the window — noop.
            return

        if action == "confirm":
            try:
                from shopman.shop.lifecycle import ensure_payment_captured

                ensure_payment_captured(order)
            except InvalidTransition as exc:
                if getattr(exc, "code", "") != "payment_not_captured":
                    raise
                deadline = _payment_deadline(order)
                if deadline and timezone.now() >= deadline:
                    from shopman.shop.services import payment as payment_service
                    from shopman.shop.services.cancellation import cancel

                    payment_service.cancel(order, reason="payment_timeout")
                    cancel(
                        order,
                        reason="payment_timeout",
                        actor="payment.timeout",
                        extra_data={"payment_timeout_at": timezone.now().isoformat()},
                    )
                    return
                message.status = "queued"
                next_try = timezone.now() + timedelta(minutes=1)
                message.available_at = min(next_try, deadline) if deadline else next_try
                message.save(update_fields=["status", "available_at", "updated_at"])
                return
            ensure_confirmable(order)
            order.transition_status(
                Order.Status.CONFIRMED, actor="confirmation.timeout",
            )
        elif action == "cancel":
            order.transition_status(
                Order.Status.CANCELLED, actor="confirmation.timeout",
            )
            logger.info(
                "confirmation.timeout: auto-cancelled order %s (auto_cancel mode)",
                order_ref,
            )
        else:
            raise DirectiveTerminalError(f"unknown action: {action!r}")


class StaleNewOrderAlertHandler:
    """Alerta o operador quando um pedido manual fica parado em NEW por muito tempo.

    Topic: order.stale_new_alert

    Disparado por :func:`_handle_confirmation` em modo `manual` (iFood etc.).
    Cria um OperatorAlert("stale_new_order") apenas se o pedido ainda estiver
    em NEW — caso já tenha sido resolvido, noop.
    """

    topic = ORDER_STALE_NEW_ALERT

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        alert_at = datetime.fromisoformat(payload["alert_at"])
        if not timezone.is_aware(alert_at):
            alert_at = timezone.make_aware(alert_at)

        if timezone.now() < alert_at:
            # Defer: not yet time, reschedule
            message.status = "queued"
            message.available_at = alert_at
            message.save(update_fields=["status", "available_at", "updated_at"])
            return

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            return

        if order.status != Order.Status.NEW:
            # Operador já resolveu — nada a fazer.
            return

        try:
            from shopman.shop.adapters import alert as alert_adapter

            alert_adapter.create(
                "stale_new_order",
                "warning",
                f"Pedido {order.ref} aguardando decisão há muito tempo",
                order_ref=order.ref,
            )
        except Exception as exc:
            raise DirectiveTransientError(str(exc)) from exc


def _payment_deadline(order) -> datetime | None:
    payment = (order.data or {}).get("payment") or {}
    expires_at = _parse_deadline(payment.get("expires_at"))
    if expires_at:
        return expires_at

    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return None

    try:
        from shopman.shop.config import ChannelConfig

        config = ChannelConfig.for_channel(order.channel_ref)
        timeout_minutes = getattr(config.payment, "timeout_minutes", 0)
    except Exception:
        logger.warning("confirmation.payment_deadline_lookup_failed order=%s", order.ref, exc_info=True)
        return None

    if timeout_minutes <= 0:
        return None
    return order.created_at + timedelta(minutes=timeout_minutes)


def _parse_deadline(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = parse_datetime(str(value))
        if dt is None:
            try:
                dt = datetime.fromisoformat(str(value))
            except ValueError:
                return None
    if not timezone.is_aware(dt):
        return timezone.make_aware(dt)
    return dt


__all__ = ["ConfirmationTimeoutHandler", "StaleNewOrderAlertHandler"]
