"""
Shopman Payment Handlers — Handlers de diretiva para pagamento.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from django.utils import timezone

from shopman.ordering.holds import release_holds_for_order
from shopman.ordering.models import Directive

from .protocols import PaymentBackend

logger = logging.getLogger(__name__)


class PaymentCaptureHandler:
    """
    Handler que captura pagamento quando Order é criada.

    Topic: payment.capture

    Comportamento idempotente:
    - Verifica se já foi capturado antes de tentar novamente
    - Re-executar não cobra 2x
    """

    topic = "payment.capture"

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order, Session

        payload = message.payload
        order_ref = payload.get("order_ref")
        intent_id = payload.get("intent_id")
        amount_q = payload.get("amount_q")

        # Busca intent_id do payload ou da session
        if not intent_id and payload.get("session_key"):
            try:
                session = Session.objects.get(
                    session_key=payload["session_key"],
                    channel__ref=payload.get("channel_ref"),
                )
                intent_id = session.data.get("payment", {}).get("intent_id")
            except Session.DoesNotExist:
                pass

        if not intent_id:
            logger.warning(
                f"PaymentCaptureHandler: No intent_id found. order_ref={order_ref}"
            )
            message.status = "failed"
            message.last_error = "no_intent_id"
            message.save()
            return

        # Verifica status atual (idempotência)
        current_status = self.backend.get_status(intent_id)
        if current_status.status == "captured":
            logger.info(
                f"PaymentCaptureHandler: Already captured. "
                f"intent_id={intent_id}, order_ref={order_ref}"
            )
            message.status = "done"
            message.save()
            return

        # Tenta capturar
        result = self.backend.capture(
            intent_id,
            amount_q=amount_q,
            reference=order_ref,
        )

        if result.success:
            logger.info(
                f"PaymentCaptureHandler: Captured successfully. "
                f"intent_id={intent_id}, order_ref={order_ref}, "
                f"transaction_id={result.transaction_id}"
            )
            message.status = "done"
            message.payload["transaction_id"] = result.transaction_id
            message.save()

            # Atualiza Order se existir
            if order_ref:
                try:
                    order = Order.objects.get(ref=order_ref)
                    order.emit_event(
                        event_type="payment.captured",
                        payload={
                            "intent_id": intent_id,
                            "transaction_id": result.transaction_id,
                            "amount_q": result.amount_q,
                        },
                        actor="payment.capture",
                    )
                except Order.DoesNotExist:
                    pass
        else:
            logger.error(
                f"PaymentCaptureHandler: Capture failed. "
                f"intent_id={intent_id}, order_ref={order_ref}, "
                f"error={result.error_code}: {result.message}"
            )
            message.status = "failed"
            message.last_error = f"{result.error_code}: {result.message}"
            message.save()


class PaymentRefundHandler:
    """
    Handler que processa reembolso.

    Topic: payment.refund
    """

    topic = "payment.refund"

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")
        intent_id = payload.get("intent_id")
        amount_q = payload.get("amount_q")
        reason = payload.get("reason")

        if not intent_id:
            message.status = "failed"
            message.last_error = "no_intent_id"
            message.save()
            return

        # Idempotency check: verify current status before refunding
        current_status = self.backend.get_status(intent_id)
        if current_status.status == "refunded":
            logger.info(
                f"PaymentRefundHandler: Already refunded. "
                f"intent_id={intent_id}, order_ref={order_ref}"
            )
            message.status = "done"
            message.save()
            return

        result = self.backend.refund(
            intent_id,
            amount_q=amount_q,
            reason=reason,
        )

        if result.success:
            logger.info(
                f"PaymentRefundHandler: Refunded successfully. "
                f"intent_id={intent_id}, refund_id={result.refund_id}, "
                f"amount_q={result.amount_q}"
            )
            message.status = "done"
            message.payload["refund_id"] = result.refund_id
            message.save()

            # Atualiza Order se existir
            if order_ref:
                try:
                    order = Order.objects.get(ref=order_ref)
                    order.emit_event(
                        event_type="payment.refunded",
                        payload={
                            "intent_id": intent_id,
                            "refund_id": result.refund_id,
                            "amount_q": result.amount_q,
                            "reason": reason,
                        },
                        actor="payment.refund",
                    )
                except Order.DoesNotExist:
                    pass
        else:
            logger.error(
                f"PaymentRefundHandler: Refund failed. "
                f"intent_id={intent_id}, error={result.error_code}: {result.message}"
            )
            message.status = "failed"
            message.last_error = f"{result.error_code}: {result.message}"
            message.save()


class PixGenerateHandler:
    """
    Gera cobrança PIX após confirmação do operador.

    Topic: pix.generate

    Idempotente: não gera segunda cobrança se order.data["payment"]["intent_id"] já existe.
    """

    topic = "pix.generate"

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        amount_q = payload["amount_q"]
        pix_timeout = payload.get("pix_timeout_minutes", 10)

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = "Order not found"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Idempotência: não gerar duas cobranças
        if order.data.get("payment", {}).get("intent_id"):
            logger.info(
                "PixGenerateHandler: intent already exists for order %s, skipping.",
                order_ref,
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        intent = self.backend.create_intent(
            amount_q=amount_q,
            currency="BRL",
            reference=order_ref,
            metadata={"pix_timeout_minutes": pix_timeout},
        )

        # Extrair QR code data — pode vir em metadata ou client_secret (JSON)
        qr_data: dict = {}
        if intent.metadata:
            qr_data = intent.metadata
        elif intent.client_secret:
            try:
                qr_data = json.loads(intent.client_secret)
            except (json.JSONDecodeError, TypeError):
                pass

        order.data["payment"] = {
            "intent_id": intent.intent_id,
            "status": intent.status,
            "amount_q": amount_q,
            "method": "pix",
            "qr_code": qr_data.get("qrcode") or qr_data.get("qr_code"),
            "copy_paste": qr_data.get("brcode") or qr_data.get("copy_paste"),
            "expires_at": intent.expires_at.isoformat() if intent.expires_at else None,
        }
        order.save(update_fields=["data", "updated_at"])

        # Criar directive de reminder (metade do timeout)
        reminder_minutes = max(pix_timeout // 2, 1)
        Directive.objects.create(
            topic="notification.send",
            payload={
                "template": "payment.reminder",
                "order_ref": order_ref,
                "amount_q": amount_q,
                "copy_paste": order.data["payment"].get("copy_paste", ""),
            },
            available_at=timezone.now() + timedelta(minutes=reminder_minutes),
        )

        # Criar directive de timeout do PIX
        pix_expires_at = timezone.now() + timedelta(minutes=pix_timeout)
        Directive.objects.create(
            topic="pix.timeout",
            payload={
                "order_ref": order_ref,
                "intent_id": intent.intent_id,
                "expires_at": pix_expires_at.isoformat(),
            },
        )

        logger.info(
            "PixGenerateHandler: PIX charge created for order %s, intent_id=%s, reminder at %dm, timeout at %dm",
            order_ref, intent.intent_id, reminder_minutes, pix_timeout,
        )
        message.status = "done"
        message.payload["intent_id"] = intent.intent_id
        message.save(update_fields=["status", "payload", "updated_at"])


class PixTimeoutHandler:
    """
    Cancela pedido se PIX não for pago em tempo.

    Topic: pix.timeout

    Idempotente: verifica status do pagamento antes de cancelar.
    Double-check no gateway para evitar race condition com webhook.
    """

    topic = "pix.timeout"

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        intent_id = payload["intent_id"]
        expires_at = datetime.fromisoformat(payload["expires_at"])

        if not timezone.is_aware(expires_at):
            expires_at = timezone.make_aware(expires_at)

        if timezone.now() < expires_at:
            message.available_at = expires_at
            message.save(update_fields=["available_at", "updated_at"])
            return

        try:
            order = Order.objects.select_related("channel").get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Verifica se pagamento já foi confirmado (idempotência)
        payment = order.data.get("payment", {})
        if payment.get("status") == "captured":
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Double-check no gateway
        status = self.backend.get_status(intent_id)
        if status.status == "captured":
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Cancela intent no gateway
        self.backend.cancel(intent_id)

        # Cancela order se ainda possível
        if order.status not in (Order.Status.CANCELLED, Order.Status.COMPLETED):
            order.transition_status(Order.Status.CANCELLED, actor="pix.timeout")

            order.data["cancellation_reason"] = "pix_timeout"
            order.save(update_fields=["data", "updated_at"])

            release_holds_for_order(order)

            Directive.objects.create(
                topic="notification.send",
                payload={
                    "order_ref": order_ref,
                    "template": "payment_expired",
                    "reason": "O prazo para pagamento PIX expirou.",
                },
            )

            logger.info("PixTimeoutHandler: order %s cancelled (pix timeout).", order_ref)

        message.status = "done"
        message.save(update_fields=["status", "updated_at"])
