"""SMS OTP sender via Comtele — Brazilian SMS provider (better BR deliverability).

Delivers the login verification code by SMS through Comtele's REST API. Chosen over a
US-number provider for native carrier delivery in Brazil and lower per-message cost.
Implements the Doorman ``send_code(target, code, method) -> bool`` contract behind the
``sms`` sender seam; swap the class in DOORMAN['DELIVERY_SENDERS']['sms'] to change provider.

Config in settings.SHOPMAN_SMS (env-driven). Inert (returns False) until api_key + route are set.
API (portal novo): POST https://api.comtele.com.br/messages/sms/send, header ``x-api-key``,
JSON {receivers:[...], message, route}. A ``route`` é o ID da rota de envio da conta
(``GET https://api.comtele.com.br/routes`` lista; use a rota transacional/Premium para OTP).
Sucesso = HTTP 200 com ``{"hasError": false, ...}``.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from ._sms import render_message, to_digits

logger = logging.getLogger(__name__)

_COMTELE_SEND_URL = "https://api.comtele.com.br/messages/sms/send"


def _get_config() -> dict:
    return getattr(settings, "SHOPMAN_SMS", {}) or {}


class ComteleSMSSender:
    """Send OTP codes by SMS via the Comtele API."""

    def send_code(self, target: str, code: str, method: str) -> bool:
        cfg = _get_config()
        api_key = cfg.get("api_key")
        route = str(cfg.get("route") or "").strip()
        if not api_key:
            logger.warning("Comtele SMS not configured (api_key) — cannot send OTP via %s", method)
            return False
        if not route:
            logger.warning("Comtele SMS not configured (route) — cannot send OTP via %s", method)
            return False

        from ._external import inert

        if inert("SHOPMAN_SMS_ALLOW_IN_DEBUG"):
            # Inerte em DEBUG → devolve False para a cadeia do Doorman cair no
            # console (o código de OTP já é exposto em dev). Opt-in real:
            # SHOPMAN_SMS_ALLOW_IN_DEBUG=true.
            logger.info("OTP SMS externo inerte (trava dev/seed) para %s — caindo para o próximo sender (console)", target)
            return False

        payload = {
            "receivers": [to_digits(target)],
            "contactGroups": [],
            "message": render_message(cfg, code),
            "route": route,
            "tag": str(cfg.get("tag") or "otp"),
        }
        request = Request(
            _COMTELE_SEND_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"x-api-key": api_key, "content-type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=cfg.get("timeout", 15)) as response:
                body = json.loads(response.read().decode("utf-8"))
                # Comtele returns HTTP 200 with {"hasError": true/false, ...}; trust the flag.
                if body.get("hasError") is False:
                    logger.info("Comtele SMS OTP sent to %s", target)
                    return True
                logger.warning("Comtele SMS rejected: %s", str(body.get("message"))[:300])
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
