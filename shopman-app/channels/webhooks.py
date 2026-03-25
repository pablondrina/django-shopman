"""
Webhook views — Recebem notificações de pagamento de gateways externos.

- EfiPixWebhookView: notificações PIX da EFI.
- StripeWebhookView: eventos do Stripe (payment_intent.succeeded, payment_failed, charge.refunded).

Usa PaymentService para persistência do lifecycle de pagamento.
"""

from __future__ import annotations

import hmac
import logging

from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.ordering.models import Order

from channels.hooks import on_payment_confirmed

logger = logging.getLogger(__name__)


def _get_efi_webhook_setting(key: str, default=None):
    cfg = getattr(settings, "SHOPMAN_EFI_WEBHOOK", {})
    defaults = {"WEBHOOK_TOKEN": None, "SKIP_SIGNATURE": False}
    return cfg.get(key, defaults.get(key, default))


class EfiPixWebhookView(APIView):
    """Endpoint para receber notificações de pagamento PIX da EFI."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response(status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        if not self._check_auth(request):
            return Response({"error": "Unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        pix_list = request.data.get("pix", [])
        if not pix_list:
            return Response({"error": "No pix data in payload"}, status=status.HTTP_400_BAD_REQUEST)

        processed = 0
        errors = 0

        for pix_item in pix_list:
            txid = pix_item.get("txid")
            e2e_id = pix_item.get("endToEndId", "")
            valor = pix_item.get("valor", "")

            if not txid:
                errors += 1
                continue

            try:
                self._process_pix_confirmation(txid=txid, e2e_id=e2e_id, valor=valor)
                processed += 1
            except Exception:
                logger.exception("EfiPixWebhook: error processing txid=%s", txid)
                errors += 1

        return Response(status=status.HTTP_200_OK)

    def _process_pix_confirmation(self, *, txid: str, e2e_id: str, valor: str) -> None:
        from shopman.payments import PaymentError, PaymentService

        # 1. Lookup intent by gateway_id (txid from Efi)
        db_intent = PaymentService.get_by_gateway_id(txid)

        if db_intent is None:
            # Fallback: lookup order directly (backward compat)
            order = (
                Order.objects.select_related("channel")
                .filter(data__payment__intent_id__icontains=txid)
                .first()
            )
            if order is None:
                return
            self._process_order_payment(order, e2e_id=e2e_id, valor=valor)
            return

        # 2. Transition intent via PaymentService: authorize → capture
        amount_q = int(round(float(valor) * 100)) if valor else db_intent.amount_q

        try:
            if db_intent.status == "pending":
                PaymentService.authorize(
                    db_intent.ref,
                    gateway_id=txid,
                    gateway_data={"e2e_id": e2e_id},
                )
            if db_intent.status in ("pending", "authorized"):
                PaymentService.capture(
                    db_intent.ref,
                    amount_q=amount_q,
                    gateway_id=txid,
                )
        except PaymentError as e:
            if e.code != "invalid_transition":
                raise
            # Already captured — idempotent

        # 3. Find and update the order
        order = (
            Order.objects.select_related("channel")
            .filter(data__payment__intent_id=db_intent.ref)
            .first()
        )

        if order is None:
            # Try by order_ref stored in the intent
            try:
                order = Order.objects.select_related("channel").get(ref=db_intent.order_ref)
            except Order.DoesNotExist:
                return

        self._process_order_payment(order, e2e_id=e2e_id, valor=valor)

    def _process_order_payment(self, order: Order, *, e2e_id: str, valor: str) -> None:
        """Update order payment data and trigger confirmation hooks."""
        payment_data = order.data.get("payment", {})
        if payment_data.get("status") == "captured":
            return

        payment_data["e2e_id"] = e2e_id
        if valor:
            payment_data["paid_amount_q"] = int(round(float(valor) * 100))
        order.data["payment"] = payment_data
        order.save(update_fields=["data", "updated_at"])

        on_payment_confirmed(order)

    def _check_auth(self, request: Request) -> bool:
        skip_signature = _get_efi_webhook_setting("SKIP_SIGNATURE")
        if skip_signature:
            return True

        expected_token = _get_efi_webhook_setting("WEBHOOK_TOKEN")
        if not expected_token:
            return True

        token = request.META.get("HTTP_X_EFI_WEBHOOK_TOKEN", "")
        if not token:
            token = request.query_params.get("token", "")

        return bool(token and hmac.compare_digest(token, expected_token))

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")


# ── Stripe Webhook ────────────────────────────────────────────────


def _get_stripe_setting(key: str, default=None):
    cfg = getattr(settings, "SHOPMAN_STRIPE", {})
    defaults = {
        "SECRET_KEY": None,
        "WEBHOOK_SECRET": None,
    }
    return cfg.get(key, defaults.get(key, default))


class StripeWebhookView(APIView):
    """
    Endpoint para receber eventos do Stripe.

    Verifica assinatura via stripe.Webhook.construct_event, delega ao
    StripeBackend.handle_webhook() para transições de pagamento.

    Eventos tratados:
    - payment_intent.succeeded  → authorize + capture
    - payment_intent.payment_failed → fail
    - charge.refunded → refund

    Eventos desconhecidos: retorna 200 (acknowledge, ignore).
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

        from channels.backends.payment_stripe import StripeBackend

        backend = StripeBackend(
            secret_key=_get_stripe_setting("SECRET_KEY"),
            webhook_secret=webhook_secret,
        )

        try:
            result = backend.handle_webhook(payload, sig_header)
        except Exception as exc:
            # stripe.error.SignatureVerificationError or similar
            logger.warning("StripeWebhook: signature verification failed: %s", exc)
            return Response(
                {"error": "Invalid signature"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        intent_ref = result.get("intent_ref")
        event_type = result.get("event_type", "")

        # For succeeded payments, trigger order-level hooks (stock commit, notification)
        if event_type == "payment_intent.succeeded" and intent_ref:
            self._trigger_order_hooks(intent_ref)

        logger.info(
            "StripeWebhook: processed event=%s intent_ref=%s",
            event_type,
            intent_ref,
        )

        return Response({"status": "ok"}, status=status.HTTP_200_OK)

    def _trigger_order_hooks(self, intent_ref: str) -> None:
        """Find associated order and trigger on_payment_confirmed hooks."""
        from shopman.payments import PaymentService

        try:
            intent = PaymentService.get(intent_ref)
        except Exception:
            return

        order = (
            Order.objects.select_related("channel")
            .filter(data__payment__intent_id=intent_ref)
            .first()
        )

        if order is None and intent.order_ref:
            try:
                order = Order.objects.select_related("channel").get(ref=intent.order_ref)
            except Order.DoesNotExist:
                return

        if order:
            on_payment_confirmed(order)
