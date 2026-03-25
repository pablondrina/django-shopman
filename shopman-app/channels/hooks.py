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
from channels.topics import CONFIRMATION_TIMEOUT, NOTIFICATION_SEND

logger = logging.getLogger(__name__)


def on_order_lifecycle(sender, order, event_type, actor, **kwargs):
    """Dispatcher genérico: lê pipeline do canal, cria directives."""
    if event_type == "created":
        _on_order_created(order)
        return

    if event_type != "status_changed":
        return

    config = ChannelConfig.effective(order.channel)
    phase = f"on_{order.status}"
    topics = getattr(config.pipeline, phase, [])

    for entry in topics:
        topic, _, template = entry.partition(":")
        payload = {"order_ref": order.ref, "channel_ref": order.channel.ref}
        if order.session_key:
            payload["session_key"] = order.session_key
        if template:
            payload["template"] = template
        Directive.objects.create(topic=topic, payload=payload)


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


def on_payment_confirmed(order):
    """
    Chamado pelo webhook de pagamento.

    Atualiza status do pagamento no order.data, dispara auto-transition
    e cria directives do pipeline on_payment_confirmed.
    """
    # Atualiza status do pagamento (safety net — webhook já pode ter feito)
    if "payment" in order.data and order.data["payment"].get("status") != "captured":
        order.data["payment"]["status"] = "captured"
        order.save(update_fields=["data", "updated_at"])

    config = ChannelConfig.effective(order.channel)

    # Auto-transition se configurada
    target = (config.flow.auto_transitions or {}).get("on_payment_confirm")
    if target and order.can_transition_to(target):
        order.transition_status(target, actor="payment.webhook")

    # Pipeline
    for entry in config.pipeline.on_payment_confirmed:
        topic, _, template = entry.partition(":")
        payload = {"order_ref": order.ref, "channel_ref": order.channel.ref}
        if order.session_key:
            payload["session_key"] = order.session_key
        if template:
            payload["template"] = template
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
