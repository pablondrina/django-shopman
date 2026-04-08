"""
Manychat webhook endpoint.

Receives webhooks from Manychat and syncs subscribers to Customers.

Flow:
    1. Validates HMAC signature (G4)
    2. Checks replay protection (G5)
    3. Calls ManychatService.sync_subscriber()
    4. Returns 200 OK
"""

from __future__ import annotations

import json
import logging

from django.conf import settings
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from shopman.guestman.gates import GateError, Gates

from .service import ManychatService

logger = logging.getLogger("guestman.manychat")


@method_decorator(csrf_exempt, name="dispatch")
class ManychatWebhookView(View):
    """
    POST endpoint for Manychat webhooks.

    Expects:
        - X-Hub-Signature-256 or X-Manychat-Signature header with HMAC
        - JSON body with subscriber data (or wrapped in "subscriber" key)

    Settings:
        MANYCHAT_WEBHOOK_SECRET — HMAC secret for signature validation.
    """

    def post(self, request):
        body = request.body
        signature = (
            request.headers.get("X-Hub-Signature-256", "")
            or request.headers.get("X-Manychat-Signature", "")
        )

        # G4: Authenticity
        secret = getattr(settings, "MANYCHAT_WEBHOOK_SECRET", "")
        try:
            Gates.provider_event_authenticity(body, signature, secret)
        except GateError as exc:
            logger.warning("Manychat webhook: G4 failed — %s", exc.message)
            return JsonResponse({"error": exc.message}, status=401)

        # Parse body
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # G5: Replay protection
        nonce = data.get("id") or data.get("event_id", "")
        if nonce:
            try:
                Gates.replay_protection(str(nonce), provider="manychat")
            except GateError:
                logger.debug("Manychat webhook: duplicate event %s", nonce)
                return JsonResponse({"status": "duplicate"}, status=200)

        # Sync subscriber
        subscriber = data.get("subscriber", data)
        try:
            customer, created = ManychatService.sync_subscriber(subscriber)
        except ValueError as exc:
            return JsonResponse({"error": str(exc)}, status=400)
        except Exception:
            logger.exception("Manychat webhook: sync failed")
            return JsonResponse({"error": "Internal error"}, status=500)

        return JsonResponse(
            {
                "status": "created" if created else "updated",
                "customer_ref": customer.ref,
            }
        )
