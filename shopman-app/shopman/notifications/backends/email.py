"""
Email Backend — Envia notificacoes via Django email.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.mail import send_mail
from django.conf import settings

from shopman.notifications.protocols import NotificationResult

logger = logging.getLogger(__name__)


class EmailBackend:
    """
    Backend para email via Django.

    Usa o sistema de email do Django (settings.EMAIL_*).

    Args:
        from_email: Email de origem (default: settings.DEFAULT_FROM_EMAIL)
        subject_prefix: Prefixo para o assunto

    Example:
        backend = EmailBackend(
            from_email="noreply@minhaloja.com",
            subject_prefix="[Minha Loja]",
        )
    """

    # Templates de assunto por evento
    SUBJECT_TEMPLATES = {
        "order.confirmed": "Pedido {order_ref} confirmado",
        "order.ready": "Pedido {order_ref} pronto para retirada",
        "order.dispatched": "Pedido {order_ref} saiu para entrega",
        "order.delivered": "Pedido {order_ref} entregue",
    }

    # Templates de corpo por evento
    BODY_TEMPLATES = {
        "order.confirmed": """
Ola{customer_name_greeting}!

Seu pedido {order_ref} foi confirmado.

Total: {total}

Obrigado pela preferencia!
""",
        "order.ready": """
Ola{customer_name_greeting}!

Seu pedido {order_ref} esta pronto para retirada.

Obrigado!
""",
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
        recipient: str,  # Email
        context: dict[str, Any],
    ) -> NotificationResult:
        """Envia email via Django."""
        subject = self._build_subject(event, context)
        body = self._build_body(event, context)

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=self.from_email,
                recipient_list=[recipient],
                fail_silently=False,
            )

            logger.info(f"Email sent: {event} -> {recipient}")
            return NotificationResult(
                success=True,
                message_id=f"email_{recipient}",
            )

        except Exception as e:
            logger.exception(f"Email error: {recipient}")
            return NotificationResult(
                success=False,
                error=str(e),
            )

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
        """Monta corpo do email."""
        # Adiciona saudacao personalizada
        ctx = dict(context)
        if ctx.get("customer_name"):
            ctx["customer_name_greeting"] = f", {ctx['customer_name']}"
        else:
            ctx["customer_name_greeting"] = ""

        template = self.BODY_TEMPLATES.get(event)

        if template:
            try:
                return template.format(**ctx)
            except KeyError:
                pass

        # Fallback generico
        return f"Evento: {event}\nPedido: {context.get('order_ref', 'N/A')}"
