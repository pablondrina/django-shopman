"""SMS OTP sender via Comtele — Brazilian SMS provider (better BR deliverability).

Delivers the login verification code by SMS through Comtele's REST API. Chosen over a
US-number provider for native carrier delivery in Brazil and lower per-message cost.
Implements the Doorman ``send_code(target, code, method) -> bool`` contract behind the
``sms`` sender seam; swap the class in DOORMAN['DELIVERY_SENDERS']['sms'] to change provider.

Config in settings.SHOPMAN_SMS (env-driven). Inert (returns False) until COMTELE_AUTH_KEY is set.
API: POST https://sms.comtele.com.br/api/v2/send, header ``auth-key``, JSON Sender/Receivers/Content.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from ._sms import render_message, to_digits

logger = logging.getLogger(__name__)

_COMTELE_SEND_URL = "https://sms.comtele.com.br/api/v2/send"


def _get_config() -> dict:
    return getattr(settings, "SHOPMAN_SMS", {}) or {}


class ComteleSMSSender:
    """Send OTP codes by SMS via the Comtele API."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        cfg = _get_config()
        auth_key = cfg.get("auth_key")
        if not auth_key:
            logger.warning("Comtele SMS not configured (auth_key) — cannot send OTP via %s", method)
            return False

        payload = {
            "Sender": str(cfg.get("sender_label") or "shopman-otp"),
            "Receivers": to_digits(target),
            "Content": render_message(cfg, code),
        }
        request = Request(
            _COMTELE_SEND_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"auth-key": auth_key, "content-type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=cfg.get("timeout", 15)) as response:
                body = json.loads(response.read().decode("utf-8"))
                # Comtele returns HTTP 200 with {"Success": true/false, ...}; trust the flag.
                if body.get("Success") is True:
                    logger.info("Comtele SMS OTP sent to %s", target)
                    return True
                logger.warning("Comtele SMS rejected: %s", str(body.get("Message"))[:300])
                return False
        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.warning("Comtele SMS send failed: HTTP %s: %s", e.code, error_body[:300])
            return False
        except URLError as e:
            logger.warning("Comtele SMS send failed: URL error: %s", e.reason)
            return False
        except Exception:  # pragma: no cover - defensive
            logger.exception("Comtele SMS send: unexpected error")
            return False
