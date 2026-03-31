"""
Payment handlers — captura, reembolso, PIX.

Handlers orquestram:
- PaymentBackend (gateway) para comunicação com provedores externos
- PaymentService (core) para persistência e lifecycle de intents
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from django.utils import timezone
from shopman.ordering.holds import release_holds_for_order
from shopman.ordering.models import Directive
from shopman.payments.protocols import PaymentBackend

from channels.topics import (
    CARD_CREATE,
    NOTIFICATION_SEND,
    PAYMENT_CAPTURE,
    PAYMENT_REFUND,
    PAYMENT_TIMEOUT,
    PIX_GENERATE,
    PIX_TIMEOUT,
)

logger = logging.getLogger(__name__)


class PaymentCaptureHandler:
    """Handler que captura pagamento. Topic: payment.capture"""

    topic = PAYMENT_CAPTURE

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order, Session
        from shopman.payments import PaymentError, PaymentService

        payload = message.payload
        order_ref = payload.get("order_ref")
        intent_id = payload.get("intent_id")
        amount_q = payload.get("amount_q")

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
            message.status = "failed"
            message.last_error = "no_intent_id"
            message.save()
            return

        # Check current status via PaymentService
        try:
            intent = PaymentService.get(intent_id)
            if intent.status == "captured":
                message.status = "done"
                message.save()
                return
        except PaymentError:
            pass

        # Capture via backend (gateway + PaymentService persistence)
        result = self.backend.capture(intent_id, amount_q=amount_q, reference=order_ref)

        if result.success:
            message.status = "done"
            message.payload["transaction_id"] = result.transaction_id
            message.save()

            if order_ref:
                try:
                    order = Order.objects.get(ref=order_ref)
                    order.emit_event(
                        event_type="payment.captured", actor="payment.capture",
                        payload={"intent_id": intent_id, "transaction_id": result.transaction_id, "amount_q": result.amount_q},
                    )
                except Order.DoesNotExist:
                    pass
        else:
            message.status = "failed"
            message.last_error = f"{result.error_code}: {result.message}"
            message.save()


class PaymentRefundHandler:
    """Handler que processa reembolso. Topic: payment.refund"""

    topic = PAYMENT_REFUND

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order
        from shopman.payments import PaymentError, PaymentService

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

        # Check current status via PaymentService
        try:
            intent = PaymentService.get(intent_id)
            if intent.status == "refunded":
                message.status = "done"
                message.save()
                return
        except PaymentError:
            pass

        # Refund via backend (gateway + PaymentService persistence)
        result = self.backend.refund(intent_id, amount_q=amount_q, reason=reason)

        if result.success:
            message.status = "done"
            message.payload["refund_id"] = result.refund_id
            message.save()

            if order_ref:
                try:
                    order = Order.objects.get(ref=order_ref)
                    order.emit_event(
                        event_type="payment.refunded", actor="payment.refund",
                        payload={"intent_id": intent_id, "refund_id": result.refund_id, "amount_q": result.amount_q, "reason": reason},
                    )
                except Order.DoesNotExist:
                    pass
        else:
            message.status = "failed"
            message.last_error = f"{result.error_code}: {result.message}"
            message.save()


class PixGenerateHandler:
    """Gera cobrança PIX após confirmação. Topic: pix.generate"""

    topic = PIX_GENERATE

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        pix_timeout = payload.get("pix_timeout_minutes", 10)

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = "Order not found"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Skip if order uses a different payment method
        chosen_method = order.data.get("payment", {}).get("method")
        if chosen_method and chosen_method != "pix":
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        if order.data.get("payment", {}).get("intent_id"):
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        amount_q = payload.get("amount_q") or order.total_q

        # Create intent via backend (gateway + PaymentService)
        intent = self.backend.create_intent(
            amount_q=amount_q, currency="BRL", reference=order_ref,
            metadata={"pix_timeout_minutes": pix_timeout},
        )

        qr_data: dict = {}
        if intent.metadata:
            qr_data = intent.metadata
        elif intent.client_secret:
            try:
                qr_data = json.loads(intent.client_secret)
            except (json.JSONDecodeError, TypeError):
                pass

        order.data["payment"] = {
            "intent_id": intent.intent_id, "status": intent.status,
            "amount_q": amount_q, "method": "pix",
            "qr_code": qr_data.get("qrcode") or qr_data.get("qr_code"),
            "copy_paste": qr_data.get("brcode") or qr_data.get("copy_paste"),
            "expires_at": intent.expires_at.isoformat() if intent.expires_at else None,
        }
        order.save(update_fields=["data", "updated_at"])

        reminder_minutes = max(pix_timeout // 2, 1)
        Directive.objects.create(
            topic=NOTIFICATION_SEND,
            payload={"template": "payment.reminder", "order_ref": order_ref, "amount_q": amount_q, "copy_paste": order.data["payment"].get("copy_paste", "")},
            available_at=timezone.now() + timedelta(minutes=reminder_minutes),
        )

        pix_expires_at = timezone.now() + timedelta(minutes=pix_timeout)
        Directive.objects.create(
            topic=PIX_TIMEOUT,
            payload={"order_ref": order_ref, "intent_id": intent.intent_id, "expires_at": pix_expires_at.isoformat()},
        )

        message.status = "done"
        message.payload["intent_id"] = intent.intent_id
        message.save(update_fields=["status", "payload", "updated_at"])


class PixTimeoutHandler:
    """Cancela pedido se PIX não for pago em tempo. Topic: pix.timeout"""

    topic = PIX_TIMEOUT

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order
        from shopman.payments import PaymentError, PaymentService

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

        payment = order.data.get("payment", {})
        if payment.get("status") == "captured":
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Check PaymentService first, then gateway as fallback
        try:
            intent = PaymentService.get(intent_id)
            if intent.status == "captured":
                message.status = "done"
                message.save(update_fields=["status", "updated_at"])
                return
        except PaymentError:
            pass

        # Also check gateway in case webhook hasn't arrived yet
        status = self.backend.get_status(intent_id)
        if status.status == "captured":
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Cancel via backend (gateway + PaymentService)
        self.backend.cancel(intent_id)

        if order.status not in (Order.Status.CANCELLED, Order.Status.COMPLETED):
            order.transition_status(Order.Status.CANCELLED, actor="pix.timeout")
            order.data["cancellation_reason"] = "pix_timeout"
            order.save(update_fields=["data", "updated_at"])
            release_holds_for_order(order)

            Directive.objects.create(
                topic=NOTIFICATION_SEND,
                payload={"order_ref": order_ref, "template": "payment_expired", "reason": "O prazo para pagamento PIX expirou."},
            )

        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


class PaymentTimeoutHandler:
    """Cancela pedido se pagamento (card, etc) não for capturado em tempo. Topic: payment.timeout"""

    topic = PAYMENT_TIMEOUT

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]
        expires_at = datetime.fromisoformat(payload["expires_at"])
        method = payload.get("method", "card")

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

        payment = order.data.get("payment", {})
        if payment.get("status") == "captured":
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Order still unpaid after timeout — cancel
        if order.status not in (Order.Status.CANCELLED, Order.Status.COMPLETED):
            order.transition_status(Order.Status.CANCELLED, actor=f"{method}.timeout")
            order.data["cancellation_reason"] = f"{method}_timeout"
            order.save(update_fields=["data", "updated_at"])
            release_holds_for_order(order)

            Directive.objects.create(
                topic=NOTIFICATION_SEND,
                payload={
                    "order_ref": order_ref,
                    "template": "payment_expired",
                    "reason": f"O prazo para pagamento por {method} expirou.",
                },
            )

        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


class CardCreateHandler:
    """Cria PaymentIntent Stripe para pagamento com cartão. Topic: card.create"""

    topic = CARD_CREATE

    def __init__(self, backend: PaymentBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload["order_ref"]

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = "Order not found"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if order.data.get("payment", {}).get("intent_id"):
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        amount_q = payload.get("amount_q") or order.total_q

        intent = self.backend.create_intent(
            amount_q=amount_q, currency="BRL", reference=order_ref,
            metadata={"method": "card"},
        )

        order.data["payment"] = {
            "intent_id": intent.intent_id,
            "status": intent.status,
            "amount_q": amount_q,
            "method": "card",
            "client_secret": intent.client_secret,
        }
        order.save(update_fields=["data", "updated_at"])

        message.status = "done"
        message.payload["intent_id"] = intent.intent_id
        message.save(update_fields=["status", "payload", "updated_at"])


__all__ = ["CardCreateHandler", "PaymentCaptureHandler", "PaymentRefundHandler", "PixGenerateHandler", "PixTimeoutHandler"]
