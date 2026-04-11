"""Stripe webhook — receives payment events from Stripe.

Uses shopman.lifecycle.dispatch(order, "on_paid") for order lifecycle.
"""

from __future__ import annotations

import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.orderman.models import Order

logger = logging.getLogger(__name__)


def _get_stripe_setting(key: str, default=None):
    cfg = getattr(settings, "SHOPMAN_STRIPE", {})
    defaults = {
        "SECRET_KEY": None,
        "WEBHOOK_SECRET": None,
    }
    return cfg.get(key, defaults.get(key, default))


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

        webhook_secret = _get_stripe_setting("WEBHOOK_SECRET")
        if not webhook_secret:
            logger.error("StripeWebhook: SHOPMAN_STRIPE.WEBHOOK_SECRET not configured")
            return Response(
                {"error": "Webhook not configured"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        from shopman.adapters.payment_stripe import handle_webhook

        try:
            result = handle_webhook(payload, sig_header)
        except Exception as exc:
            logger.warning("StripeWebhook: signature verification failed: %s", exc)
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        intent_ref = result.get("intent_ref")
        event_type = result.get("event_type", "")

        if event_type == "payment_intent.succeeded" and intent_ref:
            self._trigger_order_hooks(intent_ref)

        logger.info(
            "StripeWebhook: processed event=%s intent_ref=%s",
            event_type,
            intent_ref,
        )

        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    def _trigger_order_hooks(self, intent_ref: str) -> None:
        """Find associated order and trigger flow dispatch."""
        from shopman.lifecycle import dispatch
        from shopman.payman import PaymentService

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

        if order:
            # Dispatch to flow for downstream effects
            dispatch(order, "on_paid")
