"""
EFI PIX Webhook — Recebe notificações de pagamento confirmado.

Fluxo:
    1. Cliente paga PIX
    2. EFI envia POST /api/webhooks/efi/pix/ com payload contendo txid + endToEndId
    3. View valida assinatura (token), encontra order pelo txid (intent_id)
    4. Chama on_payment_confirmed() → auto-transition + stock.commit + notification
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

from shopman.confirmation.hooks import on_payment_confirmed
from shopman.ordering.models import Order

logger = logging.getLogger(__name__)


def _get_efi_webhook_setting(key: str, default=None):
    """Retrieve EFI webhook settings from SHOPMAN_EFI_WEBHOOK."""
    cfg = getattr(settings, "SHOPMAN_EFI_WEBHOOK", {})
    defaults = {
        "WEBHOOK_TOKEN": None,
        "SKIP_SIGNATURE": False,
    }
    return cfg.get(key, defaults.get(key, default))


class EfiPixWebhookView(APIView):
    """
    Endpoint para receber notificações de pagamento PIX da EFI.

    POST /api/webhooks/efi/pix/
        Recebe callback quando um PIX é pago.
        Payload EFI (padrão Bacen):
        {
            "pix": [
                {
                    "endToEndId": "E12345678...",
                    "txid": "<txid da cobrança>",
                    "valor": "10.50",
                    "horario": "2026-03-20T10:00:00.000Z",
                    "infoPagador": "...",
                    "chave": "<chave pix>"
                }
            ]
        }

    GET /api/webhooks/efi/pix/
        Health check usado pela EFI para validar o endpoint.
        Retorna 200 com corpo vazio.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        """Health check — EFI chama GET para validar o endpoint ao registrar webhook."""
        return Response(status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        # 1. Validate auth
        if not self._check_auth(request):
            logger.warning("EfiPixWebhook: auth failed, ip=%s", self._get_client_ip(request))
            return Response(
                {"error": "Unauthorized"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # 2. Parse payload
        pix_list = request.data.get("pix", [])
        if not pix_list:
            logger.warning("EfiPixWebhook: empty pix list in payload")
            return Response(
                {"error": "No pix data in payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Process each pix notification (usually 1, but can be batched)
        processed = 0
        errors = 0

        for pix_item in pix_list:
            txid = pix_item.get("txid")
            e2e_id = pix_item.get("endToEndId", "")
            valor = pix_item.get("valor", "")

            if not txid:
                logger.warning("EfiPixWebhook: pix item without txid, skipping. e2e=%s", e2e_id)
                errors += 1
                continue

            try:
                self._process_pix_confirmation(txid=txid, e2e_id=e2e_id, valor=valor)
                processed += 1
            except Exception:
                logger.exception("EfiPixWebhook: error processing txid=%s", txid)
                errors += 1

        logger.info("EfiPixWebhook: processed=%d, errors=%d", processed, errors)
        return Response(status=status.HTTP_200_OK)

    def _process_pix_confirmation(self, *, txid: str, e2e_id: str, valor: str) -> None:
        """
        Processa confirmação de um PIX individual.

        Idempotente: se o pagamento já está captured, ignora.
        """
        # Encontra order pelo intent_id (txid)
        order = (
            Order.objects
            .select_related("channel")
            .filter(data__payment__intent_id=txid)
            .first()
        )

        if order is None:
            logger.warning(
                "EfiPixWebhook: no order found for txid=%s, e2e=%s. "
                "Possibly already processed or orphaned.",
                txid, e2e_id,
            )
            return

        # Idempotência: já processado?
        payment_data = order.data.get("payment", {})
        if payment_data.get("status") == "captured":
            logger.info(
                "EfiPixWebhook: order %s already captured, skipping. txid=%s",
                order.ref, txid,
            )
            return

        # Enrich payment data com info do webhook
        payment_data["e2e_id"] = e2e_id
        if valor:
            payment_data["paid_amount_q"] = int(round(float(valor) * 100))
        order.data["payment"] = payment_data
        order.save(update_fields=["data", "updated_at"])

        # Delega para o hook de confirmação
        on_payment_confirmed(order)

        logger.info(
            "EfiPixWebhook: payment confirmed for order %s, txid=%s, e2e=%s, valor=%s",
            order.ref, txid, e2e_id, valor,
        )

    def _check_auth(self, request: Request) -> bool:
        """
        Valida autenticação do webhook.

        Estratégias (em ordem):
        1. mTLS — EFI usa certificado cliente (validado no proxy/nginx)
        2. Token — Header ou query param (fallback para dev/sandbox)
        3. HMAC — Assinatura do payload (se configurado)

        Em produção, mTLS é validado pelo nginx/proxy reverso.
        O endpoint só precisa verificar o token como segunda camada.
        """
        skip_signature = _get_efi_webhook_setting("SKIP_SIGNATURE")
        if skip_signature:
            return True

        expected_token = _get_efi_webhook_setting("WEBHOOK_TOKEN")
        if not expected_token:
            # Sem token configurado = auth desabilitada (dev mode)
            return True

        # Check token in header or query param
        token = request.META.get("HTTP_X_EFI_WEBHOOK_TOKEN", "")
        if not token:
            token = request.query_params.get("token", "")

        if token and hmac.compare_digest(token, expected_token):
            return True

        return False

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP from request."""
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.META.get("REMOTE_ADDR", "")
