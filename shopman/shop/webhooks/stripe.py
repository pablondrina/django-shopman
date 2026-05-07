"""Stripe webhook — receives payment events from Stripe.

Uses shopman.lifecycle.dispatch(order, "on_paid") for order lifecycle.
"""

from __future__ import annotations

import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.orderman.models import Order

from shopman.shop.services import webhook_idempotency

logger = logging.getLogger(__name__)


def _get_stripe_setting(key: str, default=None):
    cfg = getattr(settings, "SHOPMAN_STRIPE", {})
    defaults = {
        "secret_key": None,
        "webhook_secret": None,
    }
    return (
        cfg.get(key)
        or cfg.get(key.lower())
        or cfg.get(key.upper())
        or defaults.get(key.lower(), default)
    )


def _event_metadata_value(event, key: str) -> str:
    data = getattr(event, "data", None)
    obj = getattr(data, "object", None)
    metadata = getattr(obj, "metadata", None) or {}
    if not hasattr(metadata, "get"):
        return ""
    value = metadata.get(key)
    return str(value or "")


@extend_schema(exclude=True)
class StripeWebhookView(APIView):
    """Endpoint para receber eventos do Stripe.

    Verifica assinatura via stripe.Webhook.construct_event, delega ao
    StripeBackend.handle_webhook() para transições de pagamento.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

        if not sig_header:
            return Response(
                {"error": "Missing Stripe-Signature header"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        webhook_secret = _get_stripe_setting("webhook_secret")
        if not webhook_secret:
            logger.error("StripeWebhook: SHOPMAN_STRIPE.webhook_secret not configured")
            return Response(
                {"error": "Webhook not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        from shopman.shop.adapters import payment_stripe

        try:
            event = payment_stripe.construct_webhook_event(payload, sig_header)
        except Exception as exc:
            logger.warning("StripeWebhook: signature verification failed: %s", exc)
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        claim = webhook_idempotency.claim(
            "webhook:stripe",
            payment_stripe.webhook_event_key(event, payload),
        )
        if claim.replayed or claim.in_progress:
            return Response(claim.response_body, status=claim.response_code)

        event_type = str(getattr(event, "type", "") or "")
        intent_ref = _event_metadata_value(event, "shopman_ref")
        order_ref = _event_metadata_value(event, "order_ref")
        try:
            result = payment_stripe.handle_webhook_event(event)

            intent_ref = result.get("intent_ref") or intent_ref
            event_type = result.get("event_type", "") or event_type

            if event_type in ("payment_intent.succeeded", "checkout.session.completed") and intent_ref:
                self._trigger_order_hooks(intent_ref)
        except Exception as exc:
            webhook_idempotency.mark_failed(claim)
            from shopman.shop.services import observability

            observability.record_webhook_failure(
                provider="stripe",
                reason="processing_failed",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                external_ref=event_type,
                order_ref=order_ref,
                exc=exc,
                context={"intent_ref": intent_ref},
            )
            logger.exception("StripeWebhook: processing failed")
            return Response(
                {"error": "Webhook processing failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        logger.info(
            "StripeWebhook: processed event=%s intent_ref=%s",
            event_type,
            intent_ref,
        )

        response_body = {"status": "ok"}
        webhook_idempotency.mark_done(claim, response_body=response_body)
        return Response(response_body, status=status.HTTP_200_OK)

    def _trigger_order_hooks(self, intent_ref: str) -> None:
        """Find associated order and trigger flow dispatch."""
        from shopman.payman import PaymentService

        from shopman.shop.lifecycle import dispatch
        from shopman.shop.services import payment as payment_service

        try:
            intent = PaymentService.get(intent_ref)
        except Exception:
            return

        order = (
            Order.objects
            .filter(data__payment__intent_ref=intent_ref)
            .first()
        )

        if order is None and intent.order_ref:
            try:
                order = Order.objects.get(ref=intent.order_ref)
            except Order.DoesNotExist:
                return

        if order and intent.status == "authorized" and order.status == Order.Status.CONFIRMED:
            method = ((order.data or {}).get("payment") or {}).get("method")
            if method == "card":
                payment_service.capture(order)
                try:
                    intent = PaymentService.get(intent_ref)
                except Exception:
                    return

        if order and payment_service.has_sufficient_captured_payment(order) is True:
            # Dispatch to flow for downstream effects.
            dispatch(order, "on_paid")
