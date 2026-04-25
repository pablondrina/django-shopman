"""
Email notification adapter — sends via Django email backend.

Tries Django template at notifications/email/{template}.html,
falls back to inline text templates.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SUBJECT_TEMPLATES: dict[str, str] = {
    "order_confirmed": "Pedido {order_ref} confirmado",
    "order_preparing": "Pedido {order_ref} em preparo",
    "order_ready_pickup": "Pedido {order_ref} pronto para retirada",
    "order_ready_delivery": "Pedido {order_ref} pronto para envio",
    "order_dispatched": "Pedido {order_ref} saiu para entrega",
    "order_delivered": "Pedido {order_ref} entregue",
    "order_cancelled": "Pedido {order_ref} cancelado",
    "payment_confirmed": "Pagamento do pedido {order_ref} confirmado",
    "payment_expired": "Pagamento do pedido {order_ref} expirado",
    "stock_alert": "Alerta de estoque: {sku}",
}

BODY_TEMPLATES: dict[str, str] = {
    "order_confirmed": (
        "Ola{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} foi confirmado.\n\n"
        "Total: {total}\n\nObrigado pela preferencia!\n"
    ),
    "order_preparing": (
        "Ola{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} esta em preparo.\n\n"
        "Avisaremos quando estiver pronto!\n"
    ),
    "order_ready_pickup": (
        "Ola{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} esta pronto para retirada.\n\n"
        "Venha buscar. Obrigado!\n"
    ),
    "order_ready_delivery": (
        "Ola{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} esta pronto e sera enviado em breve.\n\n"
        "Obrigado!\n"
    ),
    "order_dispatched": (
        "Ola{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} saiu para entrega.\n\n"
        "Acompanhe pelo link de rastreamento.\n"
    ),
    "order_delivered": (
        "Ola{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} foi entregue.\n\nObrigado pela preferencia!\n"
    ),
    "order_cancelled": (
        "Ola{customer_name_greeting}!\n\n"
        "Seu pedido {order_ref} foi cancelado.\n\n"
        "Em caso de duvidas, entre em contato.\n"
    ),
    "payment_confirmed": (
        "Ola{customer_name_greeting}!\n\n"
        "O pagamento do pedido {order_ref} foi confirmado.\n\nObrigado!\n"
    ),
    "payment_expired": (
        "Ola{customer_name_greeting}!\n\n"
        "O prazo de pagamento do pedido {order_ref} expirou.\n\n"
        "Caso ainda deseje comprar, faca um novo pedido.\n"
    ),
    "stock_alert": (
        "Alerta de estoque\n\n"
        "Produto: {sku}\nQuantidade atual: {available}\n"
        "Minimo configurado: {min_quantity}\n\nProvidencie reposicao.\n"
    ),
}


def _enrich_context(context: dict[str, Any]) -> dict[str, Any]:
    """Add computed fields to template context."""
    ctx = dict(context)

    if ctx.get("customer_name"):
        ctx["customer_name_greeting"] = f", {ctx['customer_name']}"
    else:
        ctx["customer_name_greeting"] = ""

    total_q = ctx.get("total_q")
    if total_q and not ctx.get("total"):
        ctx["total"] = f"R$ {total_q / 100:,.2f}"

    return ctx


def _render_html(template: str, context: dict[str, Any]) -> str | None:
    """Try to render a Django HTML template for this event."""
    template_name = f"notifications/email/{template}.html"
    try:
        return render_to_string(template_name, _enrich_context(context))
    except TemplateDoesNotExist:
        return None


def send(recipient: str, template: str, context: dict | None = None, **config) -> bool:
    """
    Send an email notification.

    Args:
        recipient: Email address.
        template: Event template name (e.g. "order_confirmed").
        context: Template variables.

    Returns:
        True if sent successfully, False otherwise.
    """
    ctx = _enrich_context(context or {})

    subject_tpl = SUBJECT_TEMPLATES.get(template, f"Notificacao: {template}")
    try:
        subject = subject_tpl.format(**ctx)
    except KeyError:
        subject = subject_tpl

    subject_prefix = config.get("subject_prefix", "")
    if subject_prefix:
        subject = f"{subject_prefix} {subject}"

    body_tpl = BODY_TEMPLATES.get(template)
    if body_tpl:
        try:
            body = body_tpl.format(**ctx)
        except KeyError:
            body = f"Evento: {template}\nPedido: {ctx.get('order_ref', 'N/A')}"
    else:
        body = f"Evento: {template}\nPedido: {ctx.get('order_ref', 'N/A')}"

    try:
        html_body = _render_html(template, context or {})
    except Exception:
        logger.debug("email: HTML render failed for template=%s, sending plain text", template, exc_info=True)
        html_body = None

    from_email = config.get("from_email") or getattr(
        settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"
    )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=from_email,
            recipient_list=[recipient],
            html_message=html_body,
            fail_silently=False,
        )
        logger.info("Email sent: %s -> %s", template, recipient)
        return True
    except Exception:
        logger.exception("Email error sending to %s", recipient)
        return False


def is_available(recipient: str | None = None, **config) -> bool:
    """Email is available if Django email backend is configured."""
    return bool(getattr(settings, "EMAIL_HOST", None) or getattr(settings, "EMAIL_BACKEND", None))
