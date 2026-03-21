from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from shopman.ordering.models import Directive, Order
from shopman.confirmation.service import (
    get_confirmation_timeout,
    get_pix_timeout,
    requires_manual_confirmation,
)

logger = logging.getLogger(__name__)


def on_order_status_changed(sender, order: Order, event_type: str, actor: str, **kwargs) -> None:
    """
    Hook conectado ao signal order_changed.

    Gera directives conforme o fluxo de confirmação:
    - NEW → cria confirmation.timeout (se canal requer confirmação manual)
    - CONFIRMED (por operador) → cria pix.generate (se canal requer prepayment PIX)
    """
    if event_type != "status_changed":
        return

    channel = order.channel

    # Confirmação otimista: confirmation.timeout agora AUTO-CONFIRMA,
    # então deve disparar o fluxo de pagamento normalmente.
    # Excluir apenas actors que NÃO devem gerar pagamento (pix.timeout = cancelamento).
    if order.status == Order.Status.CONFIRMED and actor not in ("pix.timeout",):
        _on_confirmed(order, channel)

    if order.status == Order.Status.CANCELLED:
        _on_cancelled(order, channel)


def on_order_created(order: Order) -> None:
    """
    Chamado após criação de um order (post-commit).

    Two paths:
    - Manual confirmation: creates confirmation.timeout (operator has N min to cancel)
    - Auto-confirm: transitions NEW → CONFIRMED immediately (POS, marketplace, e-commerce)
    """
    channel = order.channel

    if requires_manual_confirmation(channel):
        timeout_minutes = get_confirmation_timeout(channel)
        expires_at = timezone.now() + timedelta(minutes=timeout_minutes)

        Directive.objects.create(
            topic="confirmation.timeout",
            payload={
                "order_ref": order.ref,
                "timeout_minutes": timeout_minutes,
                "expires_at": expires_at.isoformat(),
            },
            available_at=expires_at,
        )

        logger.info(
            "on_order_created: confirmation.timeout directive created for order %s (%d min).",
            order.ref, timeout_minutes,
        )
    else:
        # Auto-confirm: no operator review needed.
        # This triggers on_order_status_changed → _on_confirmed()
        # which creates pix.generate if channel requires prepayment.
        order.transition_status(Order.Status.CONFIRMED, actor="auto_confirm")
        logger.info(
            "on_order_created: order %s auto-confirmed (channel %s).",
            order.ref, channel.ref,
        )


def _on_confirmed(order: Order, channel) -> None:
    """Operador confirmou → gerar PIX se canal requer prepayment."""
    payment_config = (channel.config or {}).get("payment", {})

    if not payment_config.get("require_prepayment"):
        return

    method = payment_config.get("method", "pix")
    if method != "pix":
        return

    pix_timeout = get_pix_timeout(channel)

    Directive.objects.create(
        topic="pix.generate",
        payload={
            "order_ref": order.ref,
            "amount_q": order.total_q,
            "pix_timeout_minutes": pix_timeout,
        },
    )

    Directive.objects.create(
        topic="notification.send",
        payload={
            "order_ref": order.ref,
            "template": "order_confirmed",
        },
    )

    logger.info(
        "on_confirmed: pix.generate directive created for order %s (timeout %d min).",
        order.ref, pix_timeout,
    )


def _on_cancelled(order: Order, channel) -> None:
    """Order cancelada — notifica se tem template."""
    # Notification is already sent by the handler that cancelled (timeout/pix.timeout)
    # This hook is a safety net for manual cancellations
    reason = order.data.get("cancellation_reason")
    if not reason:
        Directive.objects.create(
            topic="notification.send",
            payload={
                "order_ref": order.ref,
                "template": "order_cancelled",
            },
        )


def on_payment_confirmed(order: Order) -> None:
    """
    Chamado quando webhook de pagamento confirma recebimento.

    Atualiza order.data e gera stock.commit + notificação.
    """
    # Atualiza status do pagamento
    if "payment" in order.data:
        order.data["payment"]["status"] = "captured"
        order.save(update_fields=["data", "updated_at"])

    # Auto-transition baseada no channel config
    auto_transitions = (order.channel.config or {}).get("order_flow", {}).get("auto_transitions", {})
    target_status = auto_transitions.get("on_payment_confirm")

    if target_status and order.can_transition_to(target_status):
        order.transition_status(target_status, actor="payment.webhook")

    # Gera stock.commit para fulfillment dos holds
    # Holds may be in order.data["holds"] (set by commit) or in the snapshot
    holds = order.data.get("holds") or (
        (order.snapshot or {}).get("data", {})
        .get("checks", {}).get("stock", {})
        .get("result", {}).get("holds", [])
    )
    if holds:
        Directive.objects.create(
            topic="stock.commit",
            payload={
                "order_ref": order.ref,
                "holds": holds,
            },
        )

    Directive.objects.create(
        topic="notification.send",
        payload={
            "order_ref": order.ref,
            "template": "payment_confirmed",
        },
    )

    logger.info("on_payment_confirmed: order %s payment confirmed, stock.commit created.", order.ref)
