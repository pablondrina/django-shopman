"""
SMS notification adapter — sends via Twilio (or any SMS provider).

Configure via settings:
    TWILIO_ACCOUNT_SID = "ACxxxxx"
    TWILIO_AUTH_TOKEN = "xxxxx"
    TWILIO_FROM_NUMBER = "+15551234567"
"""

from __future__ import annotations

import json
import logging
from base64 import b64encode
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

MESSAGE_TEMPLATES: dict[str, str] = {
    "order_received": "Recebemos o pedido {order_ref}. O estabelecimento vai conferir a disponibilidade.",
    "order_confirmed": "Pedido {order_ref} confirmado! Total: {total}",
    "order_preparing": "Pedido {order_ref} em preparo! Avisaremos quando estiver pronto.",
    "order_ready_pickup": "Pedido {order_ref} pronto para retirada!",
    "order_ready_delivery": "Pedido {order_ref} pronto! Sera enviado em breve.",
    "order_dispatched": "Pedido {order_ref} saiu para entrega!",
    "order_delivered": "Pedido {order_ref} entregue. Obrigado!",
    "order_cancelled": "Pedido {order_ref} cancelado. Em caso de duvidas, entre em contato.",
    "order_rejected": "Pedido {order_ref} nao foi confirmado pelo estabelecimento. Motivo: {reason}",
    "payment_confirmed": "Pagamento do pedido {order_ref} recebido. Seu pedido seguira para preparo.",
    "payment_requested": "Pedido {order_ref}: disponibilidade confirmada. Pague aqui: {payment_url}",
    "payment_expired": "Pedido {order_ref} cancelado: o prazo de pagamento expirou.",
    "payment_failed": "Nao conseguimos preparar o pagamento do pedido {order_ref}. Tente novamente: {payment_url}",
}

_TWILIO_API_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


def _get_config() -> dict:
    return {
        "account_sid": getattr(settings, "TWILIO_ACCOUNT_SID", ""),
        "auth_token": getattr(settings, "TWILIO_AUTH_TOKEN", ""),
        "from_number": getattr(settings, "TWILIO_FROM_NUMBER", ""),
    }


def _build_message(template: str, context: dict) -> str:
    tpl = MESSAGE_TEMPLATES.get(template)
    if tpl:
        try:
            return tpl.format(**context)
        except KeyError:
            pass
    return f"Shopman: {template} - {context.get('order_ref', 'N/A')}"


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    """
    Send an SMS notification via Twilio.

    Args:
        recipient: Phone number in E.164 format (+5511999999999).
        template: Event template name (e.g. "order_confirmed").
        context: Template variables.

    Returns:
        True if sent successfully, False otherwise.
    """
    cfg = _get_config()
    account_sid = cfg["account_sid"]
    auth_token = cfg["auth_token"]
    from_number = cfg["from_number"]

    if not account_sid or not from_number:
        logger.warning("SMS adapter: Twilio not configured")
        return False

    message = _build_message(template, context or {})
    url = _TWILIO_API_URL.format(sid=account_sid)
    payload = urlencode({"To": recipient, "From": from_number, "Body": message}).encode("utf-8")
    credentials = b64encode(f"{account_sid}:{auth_token}".encode()).decode("ascii")

    try:
        request = Request(
            url,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}",
            },
            method="POST",
        )
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
            message_sid = data.get("sid", "")
            logger.info("SMS sent: %s -> %s (sid=%s)", template, recipient, message_sid)
            return True
    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        logger.error("Twilio HTTP error: %s - %s", e.code, error_body)
        return False
    except Exception:
        logger.exception("SMS send error")
        return False


def is_available(recipient: str | None = None, **config) -> bool:
    """Check if SMS adapter is configured and available."""
    cfg = _get_config()
    return bool(cfg["account_sid"] and cfg["from_number"])
