"""iFood marketplace webhook — receives real order callbacks.

Authentication contract
-----------------------

iFood authenticates itself to this endpoint via a shared token, passed
either in the ``X-IFood-Webhook-Token`` header or a ``token`` query
parameter. The token is verified with :func:`hmac.compare_digest`.

The **same code path runs in dev and prod** — there is no "skip
signature" flag. A developer must set ``IFOOD_WEBHOOK_TOKEN`` in the
environment (including local ``.env``) to any non-empty value. If the
token is not configured, all requests are rejected with 403 — in any
environment. That is deliberate: the "correct" integration is the one
that runs, full stop.

Dev simulation (the ``inject_simulated_ifood_order`` admin action and
the storefront checkout button) remains a developer tool that calls
:func:`shopman.shop.services.ifood_ingest.ingest` directly. This webhook
reuses the exact same ingest entry point, so a real callback and a
simulated one produce identical orders.

Idempotency
-----------

Replays are detected via :attr:`Order.external_ref` scoped to the iFood
channel. A duplicate ``order_id`` returns 200 with
``{"status": "already_processed", ...}`` — not 409 — so iFood's retry
logic stops without alerting.
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

from shopman.orderman.models import Order
from shopman.shop.services import ifood_ingest

logger = logging.getLogger(__name__)


def _get_ifood_setting(key: str, default=None):
    cfg = getattr(settings, "SHOPMAN_IFOOD", {})
    return cfg.get(key, default)


class IFoodWebhookView(APIView):
    """Endpoint para notificações reais de pedidos do marketplace iFood."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        if not self._check_auth(request):
            return Response(
                {
                    "detail": "Invalid or missing iFood webhook token.",
                    "error_code": "invalid_token",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        payload = request.data
        if not isinstance(payload, dict):
            return Response(
                {
                    "detail": "Payload must be a JSON object.",
                    "error_code": "invalid_payload",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        external_ref = payload.get("order_id") or payload.get("order_code")
        if not external_ref:
            return Response(
                {
                    "detail": "order_id is required.",
                    "error_code": "missing_order_id",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing = (
            Order.objects.filter(
                channel_ref=ifood_ingest.IFOOD_CHANNEL_REF,
                external_ref=external_ref,
            )
            .only("ref")
            .first()
        )
        if existing is not None:
            logger.info(
                "ifood_webhook: replay detected for external_ref=%s (order=%s)",
                external_ref,
                existing.ref,
            )
            return Response(
                {"status": "already_processed", "order_ref": existing.ref},
                status=status.HTTP_200_OK,
            )

        ingest_payload = self._to_ingest_payload(payload, external_ref)
        logger.debug("ifood_webhook: ingesting payload=%s", ingest_payload)

        try:
            order = ifood_ingest.ingest(ingest_payload)
        except ifood_ingest.IFoodIngestError as e:
            logger.warning(
                "ifood_webhook: ingest rejected external_ref=%s code=%s message=%s",
                external_ref,
                e.code,
                e.message,
            )
            return Response(
                {"detail": e.message, "error_code": e.code},
                status=status.HTTP_400_BAD_REQUEST,
            )

        logger.info(
            "ifood_webhook: order %s created from external_ref=%s",
            order.ref,
            external_ref,
        )
        return Response(
            {"status": "accepted", "order_ref": order.ref},
            status=status.HTTP_200_OK,
        )

    def _check_auth(self, request: Request) -> bool:
        """Validate shared token. Same code path in dev and prod.

        Returns ``True`` iff the configured token is non-empty and matches
        the token presented by the caller (header or query). Every other
        case returns ``False`` and the caller gets 403.
        """
        expected = _get_ifood_setting("webhook_token") or ""
        if not expected:
            logger.error(
                "ifood_webhook: SHOPMAN_IFOOD['webhook_token'] não configurado — "
                "rejeitando. Defina IFOOD_WEBHOOK_TOKEN no ambiente (incluindo dev).",
            )
            return False

        token = request.META.get("HTTP_X_IFOOD_WEBHOOK_TOKEN", "")
        if not token:
            token = request.query_params.get("token", "")

        if not token:
            logger.warning("ifood_webhook: token ausente — rejeitando")
            return False

        if not hmac.compare_digest(token, expected):
            logger.warning("ifood_webhook: token mismatch — rejeitando")
            return False

        return True

    @staticmethod
    def _to_ingest_payload(payload: dict, external_ref: str) -> dict:
        """Translate iFood-native callback shape to the canonical ingest payload.

        iFood's callback uses ``order_id`` as the external identifier;
        :func:`ifood_ingest.ingest` expects ``order_code``. Other fields
        (``merchant_id``, ``customer``, ``delivery``, ``items``, ``notes``)
        pass through unchanged. ``total`` and ``status`` from the callback
        are intentionally ignored — we recompute totals from items and let
        the channel's :class:`ChannelConfig` drive status transitions.
        """
        return {
            "order_code": external_ref,
            "merchant_id": payload.get("merchant_id") or _get_ifood_setting("merchant_id", ""),
            "created_at": payload.get("created_at"),
            "customer": payload.get("customer") or {},
            "delivery": payload.get("delivery") or {"type": "DELIVERY", "address": ""},
            "items": payload.get("items") or [],
            "notes": payload.get("notes") or payload.get("observations") or "",
        }
