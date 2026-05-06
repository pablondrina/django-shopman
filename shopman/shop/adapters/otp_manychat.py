"""ManyChat OTP sender — delivers verification codes via WhatsApp (ManyChat).

Uses the same ManyChat API infrastructure as the notification adapter and sends
the code as direct content. Notification flows remain in notification_manychat;
OTP deliberately stays simple.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_config() -> dict:
    return getattr(settings, "SHOPMAN_MANYCHAT", {})


def _resolve_subscriber(phone: str, config: dict) -> int | None:
    """Resolve phone to ManyChat subscriber ID."""
    if phone.isdigit():
        return int(phone)

    resolver_path = config.get("resolver")
    if not resolver_path:
        return None

    from django.utils.module_loading import import_string

    resolver = import_string(resolver_path)
    return resolver(phone)


class ManychatOTPSender:
    """Send OTP codes via ManyChat WhatsApp direct content."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        """Send OTP code to phone via ManyChat.

        Args:
            target: Phone number (E.164) or ManyChat subscriber ID.
            code: 6-digit verification code.
            method: Delivery method ("whatsapp").

        Returns:
            True if sent successfully.
        """
        config = _get_config()
        api_token = config.get("api_token")
        if not api_token:
            logger.warning("ManyChat API token not configured — cannot send OTP")
            return False

        subscriber_id = _resolve_subscriber(target, config)
        if subscriber_id is None:
            logger.warning("Could not resolve ManyChat subscriber for OTP: %s", target)
            return False

        return self._send_via_text(subscriber_id, code, config)

    def _send_via_text(self, subscriber_id: int, code: str, config: dict) -> bool:
        """Send OTP as a direct ManyChat content message."""
        message = f"Seu codigo de verificacao: {code}"
        payload = {
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {
                    "messages": [{"type": "text", "text": message}],
                },
            },
        }
        return self._api_call("/sending/sendContent", payload, config)

    def _api_call(self, endpoint: str, payload: dict, config: dict) -> bool:
        base_url = config.get("base_url", "https://api.manychat.com/fb")
        api_token = config["api_token"]
        timeout = config.get("timeout", 15)

        url = f"{base_url}{endpoint}"
        data = json.dumps(payload).encode("utf-8")
        request = Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_token}",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=timeout) as response:
                resp_data = json.loads(response.read().decode("utf-8"))
                if resp_data.get("status") == "success":
                    logger.info(
                        "OTP sent via ManyChat to subscriber %s",
                        payload.get("subscriber_id"),
                    )
                    return True
                logger.warning("ManyChat OTP failed: %s", resp_data.get("message"))
                return False
        except HTTPError as e:
            error_body = e.read().decode("utf-8") if e.fp else ""
            logger.warning("ManyChat OTP HTTP error %s: %s", e.code, error_body[:200])
            return False
        except URLError as e:
            logger.warning("ManyChat OTP URL error: %s", e.reason)
            return False
        except Exception:
            logger.exception("ManyChat OTP unexpected error")
            return False
