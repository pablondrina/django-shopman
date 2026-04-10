"""EFI PIX webhook — receives payment notifications from EFI gateway.

Uses shopman.flows.dispatch(order, "on_paid") for order lifecycle.
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

from shopman.omniman.models import Order

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
        from shopman.payman import PaymentError, PaymentService

        db_intent = PaymentService.get_by_gateway_id(txid)

        if db_intent is None:
            order = (
                Order.objects.select_related("channel")
                .filter(data__payment__intent_ref__icontains=txid)
                .first()
            )
            if order is None:
                return
            self._process_order_payment(order, e2e_id=e2e_id, valor=valor)
            return

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

        order = (
            Order.objects.select_related("channel")
            .filter(data__payment__intent_ref=db_intent.ref)
            .first()
        )

        if order is None:
            try:
                order = Order.objects.select_related("channel").get(ref=db_intent.order_ref)
            except Order.DoesNotExist:
                return

        self._process_order_payment(order, e2e_id=e2e_id, valor=valor)

    def _process_order_payment(self, order: Order, *, e2e_id: str, valor: str) -> None:
        """Record PIX transaction data and trigger flow dispatch."""
        from shopman.flows import dispatch

        payment_data = order.data.get("payment", {})

        # Idempotency: if this e2e_id was already processed, skip.
        # e2e_id is the end-to-end transaction ID — unique per PIX transaction.
        if e2e_id and payment_data.get("e2e_id") == e2e_id:
            return

        # Record PIX transaction audit data (not payment status — Payman is canonical)
        if e2e_id:
            payment_data["e2e_id"] = e2e_id
        if valor:
            payment_data["paid_amount_q"] = int(round(float(valor) * 100))
        order.data["payment"] = payment_data
        order.save(update_fields=["data", "updated_at"])

        # Auto-transition if configured on channel
        self._auto_transition(order)

        # Dispatch to flow for downstream effects (stock fulfill, notification, etc.)
        dispatch(order, "on_paid")

    @staticmethod
    def _auto_transition(order: Order) -> None:
        """No-op — auto-transition is handled by dispatch(order, 'on_paid')."""
        pass

    def _check_auth(self, request: Request) -> bool:
        skip_signature = _get_efi_webhook_setting("SKIP_SIGNATURE")
        if skip_signature:
            return True

        expected_token = _get_efi_webhook_setting("WEBHOOK_TOKEN")
        if not expected_token:
            logger.error("EfiPixWebhook: WEBHOOK_TOKEN not configured — rejecting request")
            return False

        token = request.META.get("HTTP_X_EFI_WEBHOOK_TOKEN", "")
        if not token:
            token = request.query_params.get("token", "")

        if not token:
            return False

        return hmac.compare_digest(token, expected_token)
