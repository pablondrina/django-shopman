"""EFI PIX webhook — receives payment notifications from EFI gateway.

Authentication contract
-----------------------

EFI authenticates itself to this endpoint in two layers:

1. **mTLS (canonical, production).** EFI's servers present a client
   certificate to a fronting proxy (nginx/traefik). The proxy validates the
   cert against EFI's CA and sets a header (configurable via
   ``SHOPMAN_EFI_WEBHOOK["mtls_header"]``, default ``X-SSL-Client-Verify``)
   to ``SUCCESS``. This is the canonical mechanism supported by EFI.

2. **Shared token (defense-in-depth, always required).** A secret shared
   between this service and the EFI dashboard, passed either in the
   ``X-Efi-Webhook-Token`` header or a ``token`` query parameter. The token
   is verified with :func:`hmac.compare_digest`.

Both layers use **the same code path in dev and prod** — there is no
"skip signature" flag. In local development, a developer must set
``EFI_WEBHOOK_TOKEN`` in ``.env`` to any non-empty value and use the test
helper that POSTs payloads with that token. The verification logic is
identical to production; only the token value differs.

If the token is not configured, all requests are rejected with 401 — in any
environment, including dev. That is deliberate: the "correct" integration is
the one that runs, full stop.

Downstream
----------

On successful authentication and payload parse, this view updates the
payment intent via :class:`PaymentService` and calls
``shopman.shop.lifecycle.dispatch(order, "on_paid")``.
"""

from __future__ import annotations

import hmac
import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import webhook_idempotency
from shopman.shop.services.pix_confirmation import confirm_pix

logger = logging.getLogger(__name__)


def _get_efi_webhook_setting(key: str, default=None):
    cfg = getattr(settings, "SHOPMAN_EFI_WEBHOOK", {})
    return cfg.get(key, default)


@extend_schema(exclude=True)
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
        if not pix_list or not isinstance(pix_list, list):
            return Response({"error": "No pix data in payload"}, status=status.HTTP_400_BAD_REQUEST)

        processed = 0
        replays = 0
        in_progress = 0
        errors = 0

        for pix_item in pix_list:
            if not isinstance(pix_item, dict):
                errors += 1
                continue

            txid = str(pix_item.get("txid") or "").strip()
            e2e_id = str(pix_item.get("endToEndId") or "").strip()
            valor = str(pix_item.get("valor") or "").strip()

            if not txid:
                errors += 1
                continue

            claim = webhook_idempotency.claim(
                "webhook:efi-pix",
                _pix_idempotency_key(txid=txid, e2e_id=e2e_id),
            )
            if claim.replayed:
                replays += 1
                continue
            if claim.in_progress:
                in_progress += 1
                continue

            try:
                confirm_pix(txid=txid, e2e_id=e2e_id, valor=valor)
                webhook_idempotency.mark_done(
                    claim,
                    response_body={"status": "processed", "txid": txid, "e2e_id": e2e_id},
                )
                processed += 1
            except Exception as exc:
                webhook_idempotency.mark_failed(claim)
                from shopman.shop.services import observability

                observability.record_webhook_failure(
                    provider="efi-pix",
                    reason="processing_failed",
                    status_code=status.HTTP_200_OK,
                    external_ref=txid,
                    exc=exc,
                    context={"txid": txid, "e2e_id": e2e_id},
                )
                logger.exception("EfiPixWebhook: error processing txid=%s", txid)
                errors += 1

        response_status = status.HTTP_409_CONFLICT if in_progress else status.HTTP_200_OK
        return Response(
            {
                "status": "ok",
                "processed": processed,
                "replays": replays,
                "in_progress": in_progress,
                "errors": errors,
            },
            status=response_status,
        )

    def _check_auth(self, request: Request) -> bool:
        """Authenticate an inbound EFI webhook.

        Always enforces the shared token check. When the proxy has already
        validated EFI's mTLS cert, the ``X-SSL-Client-Verify`` header (or
        whatever is configured in ``SHOPMAN_EFI_WEBHOOK["mtls_header"]``)
        arrives with value ``SUCCESS`` and is logged as additional evidence
        — but the token is still checked on every request, so that dev
        environments (where no proxy exists) use the exact same code path.

        Returns ``True`` if and only if the token is configured and matches.
        Returns ``False`` (→ 401 to the caller) in every other case.
        """
        expected_token = _get_efi_webhook_setting("webhook_token") or ""
        if not expected_token:
            logger.error(
                "EfiPixWebhook: SHOPMAN_EFI_WEBHOOK['webhook_token'] is not "
                "configured — rejecting request. Set EFI_WEBHOOK_TOKEN in the "
                "environment (including local dev) to enable this endpoint.",
            )
            return False

        # Defense-in-depth: if the proxy signalled successful mTLS, log it.
        # Absence is fine in dev; presence in prod just means an extra layer
        # passed before we even got here.
        mtls_header = _get_efi_webhook_setting("mtls_header") or "HTTP_X_SSL_CLIENT_VERIFY"
        mtls_status = request.META.get(mtls_header, "")
        if mtls_status:
            logger.debug("EfiPixWebhook: mTLS pre-auth header %s=%s", mtls_header, mtls_status)

        token = request.META.get("HTTP_X_EFI_WEBHOOK_TOKEN", "")
        if not token:
            token = request.query_params.get("token", "")

        if not token:
            logger.warning("EfiPixWebhook: missing token — rejecting")
            return False

        if not hmac.compare_digest(token, expected_token):
            logger.warning("EfiPixWebhook: token mismatch — rejecting")
            return False

        return True


def _pix_idempotency_key(*, txid: str, e2e_id: str) -> str:
    if e2e_id:
        return f"e2e:{webhook_idempotency.stable_webhook_key(e2e_id)}"
    return f"txid:{webhook_idempotency.stable_webhook_key(txid)}"
