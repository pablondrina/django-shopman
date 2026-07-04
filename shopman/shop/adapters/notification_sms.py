"""SMS notification adapter — envia via Comtele (provedor BR, mesma conta do OTP).

Config em ``settings.SHOPMAN_SMS`` (env-driven, compartilhada com o OTP do
Doorman): ``api_key`` (header ``x-api-key``), ``route`` (ID da rota de envio da
conta — usar a transacional/Premium) e ``timeout``. Inerte (``is_available``
False) até api_key + route estarem setados.

API: POST https://api.comtele.com.br/messages/sms/send com JSON
``{receivers: [...], message, route, tag}``. Sucesso = HTTP 200 com
``{"hasError": false, ...}``.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

from ._sms import to_digits

logger = logging.getLogger(__name__)

MESSAGE_TEMPLATES: dict[str, str] = {
    "order_received": "Recebemos o pedido {order_ref}. O estabelecimento vai conferir a disponibilidade.",
    "order_confirmed": "Pedido {order_ref} confirmado! Total: {total}",
    "order_preparing": "Pedido {order_ref} em preparo! Avisaremos quando estiver pronto.",
    "order_ready_pickup": "Pedido {order_ref} pronto para retirada!",
    "order_ready_delivery": "Pedido {order_ref} pronto! Sera enviado em breve.",
    "order_dispatched": "Pedido {order_ref} saiu para entrega!",
    "order_delivered": "Pedido {order_ref} entregue. Obrigado!",
    "order_cancelled": "Pedido {order_ref} cancelado. Em caso de duvidas, entre em contato.{reason_note}",
    "order_rejected": "Pedido {order_ref} nao foi confirmado pelo estabelecimento. Motivo: {reason}",
    "payment_confirmed": "Pagamento do pedido {order_ref} recebido. Seu pedido seguira para preparo.",
    "payment_requested": "Pedido {order_ref}: disponibilidade confirmada. Pague aqui: {payment_url}",
    "payment_expired": "Pedido {order_ref} cancelado: o prazo de pagamento expirou.",
    "payment_failed": "Nao conseguimos preparar o pagamento do pedido {order_ref}. Tente novamente: {payment_url}",
    "preorder_reminder": "Lembrete: seu pedido {order_ref} esta agendado para amanha. Ja estamos preparando tudo!",
}

_COMTELE_SEND_URL = "https://api.comtele.com.br/messages/sms/send"


def _get_config() -> dict:
    return getattr(settings, "SHOPMAN_SMS", {}) or {}


def _build_message(template: str, context: dict) -> str:
    # O texto editado no Admin (NotificationTemplate) vale para SMS também.
    from shopman.shop.adapters._notification_templates import render_message

    return render_message(template, context, MESSAGE_TEMPLATES)


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    """
    Send an SMS notification via Comtele.

    Args:
        recipient: Phone number (E.164 ou dígitos).
        template: Event template name (e.g. "order_confirmed").
        context: Template variables.

    Returns:
        True if sent successfully, False otherwise.
    """
    cfg = _get_config()
    api_key = cfg.get("api_key")
    route = str(cfg.get("route") or "").strip()
    if not api_key or not route:
        logger.warning("SMS adapter: Comtele não configurado (api_key/route)")
        return False

    from ._external import inert

    if inert("SHOPMAN_SMS_ALLOW_IN_DEBUG"):
        logger.info(
            "SMS externo inerte (trava dev/seed): %s -> %s",
            template, recipient,
        )
        return True

    message = _build_message(template, context or {})
    payload = {
        "receivers": [to_digits(recipient)],
        "contactGroups": [],
        "message": message,
        "route": route,
        "tag": str(cfg.get("notification_tag") or "notification"),
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
            # Comtele responde HTTP 200 com {"hasError": true/false}; confiar na flag.
            if body.get("hasError") is False:
                logger.info("SMS sent via Comtele: %s -> %s", template, recipient)
                return True
            logger.warning("Comtele SMS rejected: %s", str(body.get("message"))[:300])
            return False
    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        logger.warning("Comtele SMS HTTP error: %s - %s", e.code, error_body[:300])
        return False
    except URLError as e:
        logger.warning("Comtele SMS URL error: %s", e.reason)
        return False
    except Exception:
        logger.exception("SMS send error")
        return False


def is_available(recipient: str | None = None, **config) -> bool:
    """Check if SMS adapter is configured and available."""
    cfg = _get_config()
    return bool(cfg.get("api_key") and str(cfg.get("route") or "").strip())
