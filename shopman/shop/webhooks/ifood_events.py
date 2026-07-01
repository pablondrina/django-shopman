"""iFood signed event webhook (WP-5, optional push path).

Polling (:mod:`shopman.shop.services.ifood_events`) is the primary, recommended
mechanism. This endpoint is the optional *push* alternative: iFood POSTs the
same lightweight events, signed with an HMAC. We validate the signature and run
the events through the exact same :func:`process_events` path as polling — so a
pushed event and a polled event produce identical orders.

Authentication
--------------

``X-IFood-Signature`` = ``HMAC-SHA256(raw_body, secret)`` in hex, compared with
:func:`hmac.compare_digest`. The secret is ``SHOPMAN_IFOOD['webhook_hmac_secret']``
(defaults to ``client_secret``). A missing/invalid signature — or an unconfigured
secret — returns **401**, in every environment.

⚠️ The exact signature scheme must be confirmed against the iFood portal's
webhook docs during homologação (the portal blocks bots, so it was not verified
live). Until then this endpoint stays unregistered unless a secret is set.

This is distinct from the legacy :class:`~shopman.shop.webhooks.ifood.IFoodWebhookView`
(dev simulation / normalized hub payload), which is left untouched.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging

from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import ifood_events

logger = logging.getLogger(__name__)


def _hmac_secret() -> str:
    cfg = getattr(settings, "SHOPMAN_IFOOD", {}) or {}
    return str(cfg.get("webhook_hmac_secret") or "").strip()


def _valid_signature(raw_body: bytes, presented: str) -> bool:
    secret = _hmac_secret()
    if not secret:
        logger.error(
            "ifood_events_webhook: SHOPMAN_IFOOD['webhook_hmac_secret'] not set — rejecting"
        )
        return False
    if not presented:
        return False
    expected = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, presented)


@extend_schema(exclude=True)
class IFoodEventsWebhookView(APIView):
    """Signed push endpoint for iFood Order Module events."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        raw_body = request.body  # read raw bytes before parsing (needed for HMAC)
        signature = request.META.get("HTTP_X_IFOOD_SIGNATURE", "")

        if not _valid_signature(raw_body, signature):
            return Response(
                {"detail": "Invalid or missing iFood signature.", "error_code": "invalid_signature"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        try:
            parsed = json.loads(raw_body or b"null")
        except ValueError:
            return Response(
                {"detail": "Body must be JSON.", "error_code": "invalid_payload"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # iFood may deliver a single event or a list.
        events = parsed if isinstance(parsed, list) else [parsed] if isinstance(parsed, dict) else []
        if not events:
            return Response(
                {"detail": "No events in body.", "error_code": "no_events"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        summary = ifood_events.process_events(events)
        return Response({"status": "processed", **summary}, status=status.HTTP_200_OK)
