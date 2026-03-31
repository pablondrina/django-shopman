"""
Email Backend — Envia notificacoes via Django email.

Suporta Django templates (channels/templates/notifications/email/)
com fallback para templates inline.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.template import TemplateDoesNotExist
from django.template.loader import render_to_string

from channels.protocols import NotificationResult

logger = logging.getLogger(__name__)


class EmailBackend:
    """
    Backend para email via Django.

    Usa o sistema de email do Django (settings.EMAIL_*).
    Tenta renderizar Django template em notifications/email/{event}.html,
    com fallback para templates inline.

    Args:
        from_email: Email de origem (default: settings.DEFAULT_FROM_EMAIL)
        subject_prefix: Prefixo para o assunto
    """

    SUBJECT_TEMPLATES = {
        "order_confirmed": "Pedido {order_ref} confirmado",
        "order_processing": "Pedido {order_ref} em preparo",
        "order_ready": "Pedido {order_ref} pronto para retirada",
        "order_dispatched": "Pedido {order_ref} saiu para entrega",
        "order_delivered": "Pedido {order_ref} entregue",
        "order_cancelled": "Pedido {order_ref} cancelado",
        "payment_confirmed": "Pagamento do pedido {order_ref} confirmado",
        "payment_expired": "Pagamento do pedido {order_ref} expirado",
        "stock_alert": "Alerta de estoque: {sku}",
        # Legacy dot-separated events
        "order.confirmed": "Pedido {order_ref} confirmado",
        "order.ready": "Pedido {order_ref} pronto para retirada",
        "order.dispatched": "Pedido {order_ref} saiu para entrega",
        "order.delivered": "Pedido {order_ref} entregue",
    }

    BODY_TEMPLATES = {
        "order_confirmed": (
            "Ola{customer_name_greeting}!\n\n"
            "Seu pedido {order_ref} foi confirmado.\n\n"
            "Total: {total}\n\n"
            "Obrigado pela preferencia!\n"
        ),
        "order_processing": (
            "Ola{customer_name_greeting}!\n\n"
            "Seu pedido {order_ref} esta em preparo.\n\n"
            "Avisaremos quando estiver pronto!\n"
        ),
        "order_ready": (
            "Ola{customer_name_greeting}!\n\n"
            "Seu pedido {order_ref} esta pronto para retirada.\n\n"
            "Obrigado!\n"
        ),
        "order_dispatched": (
            "Ola{customer_name_greeting}!\n\n"
            "Seu pedido {order_ref} saiu para entrega.\n\n"
            "Acompanhe pelo link de rastreamento.\n"
        ),
        "order_delivered": (
            "Ola{customer_name_greeting}!\n\n"
            "Seu pedido {order_ref} foi entregue.\n\n"
            "Obrigado pela preferencia!\n"
        ),
        "order_cancelled": (
            "Ola{customer_name_greeting}!\n\n"
            "Seu pedido {order_ref} foi cancelado.\n\n"
            "Em caso de duvidas, entre em contato.\n"
        ),
        "payment_confirmed": (
            "Ola{customer_name_greeting}!\n\n"
            "O pagamento do pedido {order_ref} foi confirmado.\n\n"
            "Obrigado!\n"
        ),
        "payment_expired": (
            "Ola{customer_name_greeting}!\n\n"
            "O prazo de pagamento do pedido {order_ref} expirou.\n\n"
            "Caso ainda deseje comprar, faca um novo pedido.\n"
        ),
        "stock_alert": (
            "Alerta de estoque\n\n"
            "Produto: {sku}\n"
            "Quantidade atual: {available}\n"
            "Minimo configurado: {min_quantity}\n\n"
            "Providencie reposicao.\n"
        ),
        # Legacy dot-separated
        "order.confirmed": (
            "Ola{customer_name_greeting}!\n\n"
            "Seu pedido {order_ref} foi confirmado.\n\n"
            "Total: {total}\n\n"
            "Obrigado pela preferencia!\n"
        ),
        "order.ready": (
            "Ola{customer_name_greeting}!\n\n"
            "Seu pedido {order_ref} esta pronto para retirada.\n\n"
            "Obrigado!\n"
        ),
    }

    def __init__(
        self,
        from_email: str | None = None,
        subject_prefix: str = "",
    ):
        self.from_email = from_email or getattr(
            settings, "DEFAULT_FROM_EMAIL", "noreply@example.com"
        )
        self.subject_prefix = subject_prefix

    def send(
        self,
        *,
        event: str,
        recipient: str,
        context: dict[str, Any],
    ) -> NotificationResult:
        """Envia email via Django."""
        subject = self._build_subject(event, context)
        body = self._build_body(event, context)

        try:
            html_body = self._render_template(event, context)
        except Exception:
            html_body = None

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=self.from_email,
                recipient_list=[recipient],
                html_message=html_body,
                fail_silently=False,
            )

            logger.info("Email sent: %s -> %s", event, recipient)
            return NotificationResult(
                success=True,
                message_id=f"email_{recipient}",
            )

        except Exception as e:
            logger.exception("Email error: %s", recipient)
            return NotificationResult(
                success=False,
                error=str(e),
            )

    def _render_template(self, event: str, context: dict[str, Any]) -> str | None:
        """Try to render a Django template for this event."""
        template_name = f"notifications/email/{event}.html"
        try:
            ctx = self._enrich_context(context)
            return render_to_string(template_name, ctx)
        except TemplateDoesNotExist:
            return None

    def _enrich_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Add computed fields to context."""
        ctx = dict(context)
        if ctx.get("customer_name"):
            ctx["customer_name_greeting"] = f", {ctx['customer_name']}"
        else:
            ctx["customer_name_greeting"] = ""

        total_q = ctx.get("total_q")
        if total_q and not ctx.get("total"):
            ctx["total"] = f"R$ {total_q / 100:,.2f}"

        try:
            from shop.models import Shop

            shop = Shop.load()
            if shop:
                ctx.setdefault("shop_name", shop.name)
        except Exception:
            ctx.setdefault("shop_name", "Shopman")

        return ctx

    def _build_subject(self, event: str, context: dict[str, Any]) -> str:
        """Monta assunto do email."""
        template = self.SUBJECT_TEMPLATES.get(event, f"Notificacao: {event}")

        try:
            subject = template.format(**context)
        except KeyError:
            subject = template

        if self.subject_prefix:
            return f"{self.subject_prefix} {subject}"
        return subject

    def _build_body(self, event: str, context: dict[str, Any]) -> str:
        """Monta corpo do email (texto plano)."""
        ctx = self._enrich_context(context)

        template = self.BODY_TEMPLATES.get(event)

        if template:
            try:
                return template.format(**ctx)
            except KeyError:
                pass

        # Fallback generico
        return f"Evento: {event}\nPedido: {context.get('order_ref', 'N/A')}"
