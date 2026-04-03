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
    "order_confirmed": (
        "Ola{customer_name_greeting}! Seu pedido {order_ref} foi confirmado."
        " Total: {total}. Obrigado pela preferencia! \U0001f950"
    ),
    "order_ready": (
        "Ola{customer_name_greeting}! Seu pedido {order_ref} esta pronto! \U0001f389"
    ),
    "order_dispatched": "Seu pedido {order_ref} saiu para entrega! \U0001f697",
    "order_delivered": "Pedido {order_ref} entregue. Obrigado! \u2b50",
    "order_cancelled": (
        "Seu pedido {order_ref} foi cancelado. Qualquer duvida, estamos aqui."
    ),
    "payment_confirmed": (
        "Ola{customer_name_greeting}! Pagamento do pedido {order_ref} confirmado!"
    ),
    "payment_reminder": (
        "Ola{customer_name_greeting}! Seu pedido {order_ref} aguarda"
        " pagamento PIX. Use o codigo: {copy_paste}"
    ),
    "payment_expired": (
        "Seu pedido {order_ref} foi cancelado pois o pagamento PIX"
        " nao foi confirmado a tempo."
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
        from importlib import import_module

        module_path, func_name = resolver_path.rsplit(".", 1)
        module = import_module(module_path)
        resolver = getattr(module, func_name)
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
        return {"success": False, "error": str(e)}


def _build_message(template: str, context: dict) -> str:
    """Build message from template + context."""
    ctx = dict(context)
    ctx["customer_name_greeting"] = (
        f", {ctx['customer_name']}" if ctx.get("customer_name") else ""
    )

    tpl = MESSAGE_TEMPLATES.get(template)
    if tpl:
        try:
            return tpl.format(**ctx)
        except KeyError:
            pass

    order_ref = context.get("order_ref", "")
    if order_ref:
        return f"Notificacao: {template} — Pedido {order_ref}"
    return f"Notificacao: {template}"


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
