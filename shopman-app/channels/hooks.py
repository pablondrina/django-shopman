"""
Channels hooks — dispatcher genérico para ciclo de vida de pedidos.

Lê pipeline do ChannelConfig e cria Directives automaticamente.
Conectado via signal do ordering.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone
from shopman.ordering.models import Directive, Order

from channels.config import ChannelConfig
from channels.topics import CONFIRMATION_TIMEOUT, NOTIFICATION_SEND, PAYMENT_REFUND, PAYMENT_TIMEOUT

logger = logging.getLogger(__name__)


def on_order_lifecycle(sender, order, event_type, actor, **kwargs):
    """Dispatcher genérico: lê pipeline do canal, cria directives."""
    if event_type == "created":
        _on_order_created(order)
        return

    if event_type != "status_changed":
        return

    if order.status == Order.Status.CANCELLED:
        _on_cancelled(order)

    config = ChannelConfig.effective(order.channel)
    phase = f"on_{order.status}"
    topics = getattr(config.pipeline, phase, [])

    for entry in topics:
        topic, _, template = entry.partition(":")
        payload = _build_directive_payload(order, template)
        Directive.objects.create(topic=topic, payload=payload)

    # Schedule payment timeout for card orders entering CONFIRMED
    # (PIX timeout is handled by PixGenerateHandler)
    if order.status == Order.Status.CONFIRMED:
        _maybe_schedule_card_timeout(order, config)


def _build_directive_payload(order, template: str = "") -> dict:
    """Build directive payload with origin_channel for notification routing."""
    payload = {"order_ref": order.ref, "channel_ref": order.channel.ref}
    if order.session_key:
        payload["session_key"] = order.session_key
    origin = (order.data or {}).get("origin_channel")
    if origin:
        payload["origin_channel"] = origin
    if template:
        payload["template"] = template
    return payload


def _on_order_created(order):
    """Confirmação: imediata, otimista, ou manual."""
    config = ChannelConfig.effective(order.channel)

    if config.confirmation.mode == "optimistic":
        expires_at = timezone.now() + timedelta(
            minutes=config.confirmation.timeout_minutes
        )
        Directive.objects.create(
            topic=CONFIRMATION_TIMEOUT,
            payload={
                "order_ref": order.ref,
                "expires_at": expires_at.isoformat(),
            },
            available_at=expires_at,
        )
    elif config.confirmation.mode == "immediate":
        order.transition_status(Order.Status.CONFIRMED, actor="auto_confirm")
    # mode == "manual": order fica em NEW até aprovação explícita


def _maybe_schedule_card_timeout(order, config: ChannelConfig):
    """Schedule payment timeout for card orders (30 min default).

    PIX timeout is handled by PixGenerateHandler. This covers card
    and other async methods where the user may abandon the payment page.
    """
    payment = order.data.get("payment", {})
    method = payment.get("method", "")

    # Skip: PIX (handled separately), counter/external (no timeout needed)
    if method in ("pix", "counter", "external", ""):
        return

    # Skip if payment already captured
    if payment.get("status") == "captured":
        return

    # Card timeout: 2x the standard payment timeout (default 30 min)
    timeout_minutes = config.payment.timeout_minutes * 2
    expires_at = timezone.now() + timedelta(minutes=timeout_minutes)

    Directive.objects.create(
        topic=PAYMENT_TIMEOUT,
        payload={
            "order_ref": order.ref,
            "intent_id": payment.get("intent_id", ""),
            "expires_at": expires_at.isoformat(),
            "method": method,
        },
        available_at=expires_at,
    )


def on_payment_confirmed(order):
    """
    Chamado pelo webhook de pagamento.

    Atualiza status do pagamento no order.data, dispara auto-transition
    e cria directives do pipeline on_payment_confirmed.

    Se order já foi cancelada (race condition), dispara refund automático.
    """
    # Atualiza status do pagamento (safety net — webhook já pode ter feito)
    if "payment" in order.data and order.data["payment"].get("status") != "captured":
        order.data["payment"]["status"] = "captured"
        order.save(update_fields=["data", "updated_at"])

    # Race condition: pagamento chegou mas pedido já foi cancelado
    if order.status == Order.Status.CANCELLED:
        intent_id = order.data.get("payment", {}).get("intent_id")
        logger.warning(
            "payment_confirmed_after_cancel order=%s intent=%s — auto-refund",
            order.ref, intent_id,
        )
        if intent_id:
            Directive.objects.create(
                topic=PAYMENT_REFUND,
                payload={
                    "order_ref": order.ref,
                    "intent_id": intent_id,
                    "amount_q": order.data.get("payment", {}).get("amount_q"),
                    "reason": "payment_after_cancel",
                },
            )
        # Escalate to operator
        try:
            from shop.models import OperatorAlert

            OperatorAlert.objects.create(
                type="payment_after_cancel",
                severity="warning",
                message=(
                    f"Pagamento confirmado após cancelamento do pedido {order.ref}. "
                    f"Reembolso automático {'criado' if intent_id else 'não criado (sem intent_id)'}."
                ),
                order_ref=order.ref,
            )
        except Exception:
            logger.exception("Failed to create OperatorAlert for payment_after_cancel")
        return

    config = ChannelConfig.effective(order.channel)

    # Auto-transition se configurada
    target = (config.flow.auto_transitions or {}).get("on_payment_confirm")
    if target and order.can_transition_to(target):
        order.transition_status(target, actor="payment.webhook")

    # Pipeline
    for entry in config.pipeline.on_payment_confirmed:
        topic, _, template = entry.partition(":")
        payload = _build_directive_payload(order, template)
        Directive.objects.create(topic=topic, payload=payload)


def _on_cancelled(order, channel=None):
    """Order cancelada — libera holds + notifica."""
    channel = channel or order.channel

    session_key = order.data.get("session_key") or order.session_key
    if session_key:
        try:
            from channels.setup import _load_stock_backend

            backend = _load_stock_backend()
            if backend and hasattr(backend, "release_holds_for_reference"):
                released = backend.release_holds_for_reference(session_key)
                if released:
                    logger.info(
                        "_on_cancelled: released %d holds for session %s (order %s)",
                        released, session_key, order.ref,
                    )
        except Exception:
            logger.warning(
                "_on_cancelled: failed to release holds for order %s",
                order.ref, exc_info=True,
            )

    # Safety net notification for manual cancellations
    reason = order.data.get("cancellation_reason")
    if not reason:
        Directive.objects.create(
            topic=NOTIFICATION_SEND,
            payload={
                "order_ref": order.ref,
                "template": "order_cancelled",
            },
        )
