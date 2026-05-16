"""
ManyChat notification adapter — WhatsApp via ManyChat API.

WhatsApp is ALWAYS via ManyChat, never Meta Cloud API directly.
"""

from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings

logger = logging.getLogger(__name__)

MESSAGE_TEMPLATES: dict[str, str] = {
    "order_received": (
        "Ola{customer_name_greeting}! Recebemos seu pedido {order_ref}. "
        "O estabelecimento vai conferir a disponibilidade. Acompanhe: {tracking_url}"
    ),
    "order_confirmed": (
        "Ola{customer_name_greeting}! Seu pedido {order_ref} foi confirmado."
        " Total: {total}. Obrigado pela preferencia! \U0001f950{tracking_suffix}"
    ),
    "order_preparing": (
        "Ola{customer_name_greeting}! Seu pedido {order_ref} esta em preparo."
        "{tracking_suffix}"
    ),
    "order_ready_pickup": (
        "Ola{customer_name_greeting}! Seu pedido {order_ref} esta pronto"
        " para retirada! \U0001f389\n\nVenha buscar. Obrigado!{tracking_suffix}"
    ),
    "order_ready_delivery": (
        "Ola{customer_name_greeting}! Seu pedido {order_ref} esta pronto"
        " e sera enviado em breve! \U0001f4e6{tracking_suffix}"
    ),
    "order_dispatched": (
        "Ola{customer_name_greeting}! Seu pedido {order_ref} saiu para"
        " entrega! \U0001f697{tracking_suffix}"
    ),
    "order_delivered": (
        "Pedido {order_ref} entregue. Obrigado pela preferencia! \u2b50{reorder_suffix}"
    ),
    "order_cancelled": (
        "Seu pedido {order_ref} foi cancelado. Qualquer duvida, estamos aqui."
    ),
    "order_rejected": (
        "Seu pedido {order_ref} nao pode ser confirmado pelo estabelecimento. "
        "Motivo: {reason}. Se precisar de ajuda, estamos aqui."
    ),
    "payment_confirmed": (
        "Ola{customer_name_greeting}! Pagamento do pedido {order_ref} recebido. "
        "Seu pedido seguira para preparo."
    ),
    "payment_requested": (
        "Ola{customer_name_greeting}! Conferimos a disponibilidade do pedido {order_ref}. "
        "Agora falta o pagamento. Acesse: {payment_url}{pix_suffix}"
    ),
    "payment_reminder": (
        "Ola{customer_name_greeting}! Seu pedido {order_ref} aguarda"
        " pagamento PIX. Use o codigo: {copy_paste}"
    ),
    "payment_expired": (
        "Seu pedido {order_ref} foi cancelado pois o pagamento PIX"
        " nao foi confirmado a tempo."
    ),
    "payment_failed": (
        "Nao conseguimos preparar o pagamento do pedido {order_ref}. "
        "Abra o link do pedido para tentar novamente: {payment_url}"
    ),
}


def _get_config() -> dict:
    """Read ManyChat configuration from settings."""
    return getattr(settings, "SHOPMAN_MANYCHAT", {})


def _resolve_subscriber(recipient: str, config: dict) -> int | None:
    """Resolve recipient to ManyChat subscriber ID."""
    if recipient.isdigit():
        return int(recipient)

    resolver_path = config.get("resolver")
    if resolver_path:
        from ._dotted import import_dotted_attr

        resolver = import_dotted_attr(resolver_path)
        return resolver(recipient)

    return None


def _api_call(endpoint: str, payload: dict, config: dict) -> dict:
    """Make authenticated request to ManyChat API."""
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
                return {
                    "success": True,
                    "message_id": f"mc_{payload.get('subscriber_id')}",
                }
            return {"success": False, "error": resp_data.get("message", "Manychat error")}
    except HTTPError as e:
        error_body = e.read().decode("utf-8") if e.fp else ""
        return {"success": False, "error": f"HTTP {e.code}: {error_body[:200]}"}
    except URLError as e:
        return {"success": False, "error": f"URL error: {e.reason}"}
    except Exception as e:
        logger.warning("manychat._send_whatsapp: unexpected error: %s", e, exc_info=True)
        return {"success": False, "error": str(e)}


def _build_message(template: str, context: dict) -> str:
    """Build message from template + context.

    Resolution order:
    1. NotificationTemplate DB record (event=template, is_active=True) → body field
    2. MESSAGE_TEMPLATES hardcoded fallback
    3. Generic fallback with order_ref
    """
    ctx = dict(context)
    ctx["customer_name_greeting"] = (
        f", {ctx['customer_name']}" if ctx.get("customer_name") else ""
    )
    ctx["tracking_suffix"] = (
        f"\nAcompanhe: {ctx['tracking_url']}" if ctx.get("tracking_url") else ""
    )
    ctx["reorder_suffix"] = (
        f"\nPeca de novo: {ctx['reorder_url']}" if ctx.get("reorder_url") else ""
    )

    # 1. Try DB template
    tpl_body = _load_db_template(template)
    if tpl_body:
        try:
            return tpl_body.format_map(_SafeFormatMap(ctx))
        except Exception:
            logger.debug("manychat._build_message: DB template format failed for %s", template, exc_info=True)

    # 2. Hardcoded fallback
    tpl = MESSAGE_TEMPLATES.get(template)
    if tpl:
        try:
            return tpl.format_map(_SafeFormatMap(ctx))
        except Exception:
            logger.debug("manychat._build_message: hardcoded template format failed for %s", template, exc_info=True)

    # 3. Generic fallback
    order_ref = context.get("order_ref", "")
    if order_ref:
        return f"Notificacao: {template} — Pedido {order_ref}"
    return f"Notificacao: {template}"


class _SafeFormatMap(dict):
    """dict subclass that returns '{key}' for missing keys instead of raising KeyError."""

    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


def _load_db_template(event: str) -> str | None:
    """Return the body of an active NotificationTemplate for the given event, or None."""
    try:
        from shopman.shop.models import NotificationTemplate

        obj = NotificationTemplate.objects.filter(event=event, is_active=True).first()
        if obj:
            return obj.body
    except Exception:
        logger.debug("manychat._load_db_template: lookup failed for event=%s", event, exc_info=True)
    return None


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    """
    Send a notification via ManyChat (WhatsApp).

    Args:
        recipient: Phone number or ManyChat subscriber ID.
        template: Event template name (e.g. "order_confirmed").
        context: Template variables (order_ref, customer_name, total, etc.).

    Returns:
        True if sent successfully, False otherwise.
    """
    mc_config = _get_config()
    if not mc_config.get("api_token"):
        logger.warning("ManyChat API token not configured")
        return False

    ctx = context or {}
    subscriber_id = _resolve_subscriber(recipient, mc_config)
    if subscriber_id is None:
        logger.warning("Could not resolve subscriber for: %s", recipient)
        return False

    flow_map = mc_config.get("flow_map", {})
    flow_ns = flow_map.get(template)

    if flow_ns:
        payload = {
            "subscriber_id": subscriber_id,
            "flow_ns": flow_ns,
            "flow_token": ctx,
        }
        result = _api_call("/sending/sendFlow", payload, mc_config)
    else:
        message = _build_message(template, ctx)
        payload = {
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {"messages": [{"type": "text", "text": message}]},
            },
        }
        result = _api_call("/sending/sendContent", payload, mc_config)

    if not result["success"]:
        logger.warning("ManyChat send failed: %s", result.get("error"))
    return result["success"]


def is_available(recipient: str | None = None, **config) -> bool:
    """Check if ManyChat adapter is configured and available."""
    mc_config = _get_config()
    return bool(mc_config.get("api_token"))
