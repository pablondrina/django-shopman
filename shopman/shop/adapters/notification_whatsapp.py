"""
WhatsApp notification adapter — Meta WhatsApp Cloud API **direct** (no ManyChat layer).

Spike for evaluating the transactional channel direct on Meta (vs the ManyChat layer in
notification_manychat). Same adapter contract: ``send(recipient, template, context)`` +
``is_available()``. Inert until WHATSAPP_PHONE_NUMBER_ID + WHATSAPP_ACCESS_TOKEN are set.

Proactive (outside the 24h customer-service window) messages MUST use a Meta-approved
template — Utility for order/payment updates, Authentication for OTP. Map each event to its
approved template via ``SHOPMAN_WHATSAPP['templates']``. With no mapping, a plain text
message is sent, which Meta only delivers inside the 24h window.

See docs/plans/WHATSAPP-TRANSACTIONAL-CHANNEL-PLAN.md.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

# Plain-text bodies reused for the inside-24h-window path (proactive sends need templates).
from .notification_manychat import _build_message

logger = logging.getLogger(__name__)


def _get_config() -> dict:
    return getattr(settings, "SHOPMAN_WHATSAPP", {}) or {}


def _to_number(recipient: str) -> str:
    """Normalize recipient to digits-only E.164 (no '+'), as the Cloud API expects."""
    return "".join(ch for ch in str(recipient) if ch.isdigit())


def _template_payload(to: str, tpl: dict, context: dict, default_lang: str) -> dict:
    """Build a Cloud API 'template' message from the event's approved-template config."""
    body_params = [
        {"type": "text", "text": str(context.get(key, ""))} for key in tpl.get("body", [])
    ]
    template: dict = {
        "name": tpl["name"],
        "language": {"code": tpl.get("lang", default_lang)},
    }
    if body_params:
        template["components"] = [{"type": "body", "parameters": body_params}]
    return {"messaging_product": "whatsapp", "to": to, "type": "template", "template": template}


def _text_payload(to: str, message: str) -> dict:
    return {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}


def _api_call(payload: dict, config: dict) -> dict:
    version = config.get("GRAPH_VERSION", "v21.0")
    phone_number_id = config["PHONE_NUMBER_ID"]
    url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['ACCESS_TOKEN']}",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=config.get("timeout", 15)) as response:
            body = json.loads(response.read().decode("utf-8"))
            messages = body.get("messages") or []
            if messages:
                return {"success": True, "message_id": messages[0].get("id", "")}
            return {"success": False, "error": f"unexpected response: {str(body)[:200]}"}
    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return {"success": False, "error": f"HTTP {e.code}: {error_body[:300]}"}
    except URLError as e:
        return {"success": False, "error": f"URL error: {e.reason}"}
    except Exception as e:  # pragma: no cover - defensive
        logger.warning("whatsapp._api_call: unexpected error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    """Send a notification via Meta WhatsApp Cloud API directly."""
    cfg = _get_config()
    if not (cfg.get("PHONE_NUMBER_ID") and cfg.get("ACCESS_TOKEN")):
        logger.warning("WhatsApp Cloud API not configured (PHONE_NUMBER_ID/ACCESS_TOKEN)")
        return False

    from ._external import inert_in_debug

    if inert_in_debug("SHOPMAN_WHATSAPP_ALLOW_IN_DEBUG"):
        logger.info(
            "WhatsApp inerte em DEBUG: %s -> %s (defina SHOPMAN_WHATSAPP_ALLOW_IN_DEBUG=true para enviar de verdade)",
            template, recipient,
        )
        return True

    ctx = context or {}
    to = _to_number(recipient)
    if not to:
        logger.warning("WhatsApp: could not resolve a phone number from: %s", recipient)
        return False

    tpl = (cfg.get("templates") or {}).get(template)
    if tpl:
        payload = _template_payload(to, tpl, ctx, cfg.get("DEFAULT_LANG", "pt_BR"))
    else:
        # No approved template mapped → plain text (delivered only inside the 24h window).
        payload = _text_payload(to, _build_message(template, ctx))

    result = _api_call(payload, cfg)
    if not result["success"]:
        logger.warning("WhatsApp Cloud API send failed: %s", result.get("error"))
    return result["success"]


def is_available(recipient: str | None = None, **config) -> bool:
    cfg = _get_config()
    return bool(cfg.get("PHONE_NUMBER_ID") and cfg.get("ACCESS_TOKEN"))
