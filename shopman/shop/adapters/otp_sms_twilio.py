"""SMS OTP sender via Twilio — delivers the verification code by SMS.

WhatsApp OTP is not viable (ManyChat has no Authentication-template category, and the
single brand number cannot be on ManyChat and the Cloud API at once), so the login code
goes by SMS — the market-standard channel for one-time codes. Implements the Doorman
``send_code(target, code, method) -> bool`` contract behind the existing ``sms`` sender seam.

Provider-agnostic by replacement: swap this class in DOORMAN['DELIVERY_SENDERS']['sms'] for a
different provider later. Config lives in settings.SHOPMAN_SMS (env-driven). Inert (returns
False) until account_sid + auth_token + a sender (from_number or messaging_service_sid) are set.
"""

from __future__ import annotations

import base64
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

from ._sms import render_message

logger = logging.getLogger(__name__)

_TWILIO_API = "https://api.twilio.com/2010-04-01"


def _get_config() -> dict:
    return getattr(settings, "SHOPMAN_SMS", {}) or {}


class TwilioSMSSender:
    """Send OTP codes by SMS via the Twilio Messaging API."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        cfg = _get_config()
        account_sid = cfg.get("account_sid")
        auth_token = cfg.get("auth_token")
        from_number = cfg.get("from_number")
        messaging_service_sid = cfg.get("messaging_service_sid")

        if not (account_sid and auth_token and (from_number or messaging_service_sid)):
            logger.warning("Twilio SMS not configured — cannot send OTP via %s", method)
            return False

        form = {"To": target, "Body": render_message(cfg, code)}
        if messaging_service_sid:
            form["MessagingServiceSid"] = messaging_service_sid
        else:
            form["From"] = from_number

        credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
        request = Request(
            f"{_TWILIO_API}/Accounts/{account_sid}/Messages.json",
            data=urlencode(form).encode("utf-8"),
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=cfg.get("timeout", 15)) as response:
                # Twilio returns 201 Created with a message resource on success.
                ok = 200 <= response.status < 300
                if ok:
                    logger.info("Twilio SMS OTP sent to %s", target)
                return ok
        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.warning("Twilio SMS send failed: HTTP %s: %s", e.code, error_body[:300])
            return False
        except URLError as e:
            logger.warning("Twilio SMS send failed: URL error: %s", e.reason)
            return False
        except Exception:  # pragma: no cover - defensive
            logger.exception("Twilio SMS send: unexpected error")
            return False
