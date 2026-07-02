"""Templates de notificação editáveis no Admin — compartilhados entre canais.

O lojista edita ``NotificationTemplate`` no Admin; TODOS os canais (WhatsApp/
ManyChat, SMS, e-mail) leem o mesmo template. Placeholder ausente vai literal
(``{chave}``) em vez de quebrar o envio — melhor mensagem imperfeita que
cliente sem aviso.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class SafeFormatMap(dict):
    """format_map que preserva ``{chave}`` desconhecida em vez de levantar KeyError."""

    def __missing__(self, key):  # pragma: no cover - trivial
        return "{" + key + "}"


def db_template(event: str) -> tuple[str | None, str | None]:
    """Retorna ``(subject, body)`` do NotificationTemplate ativo, ou ``(None, None)``."""
    try:
        from shopman.shop.models import NotificationTemplate

        obj = NotificationTemplate.objects.filter(event=event, is_active=True).first()
        if obj:
            return (obj.subject or None, obj.body or None)
    except Exception:
        logger.debug("notification_templates: lookup failed for event=%s", event, exc_info=True)
    return (None, None)


def render_message(event: str, context: dict, fallback_templates: dict[str, str]) -> str:
    """Corpo da mensagem: Admin (DB) → fallback hardcoded do canal → genérico."""
    ctx = SafeFormatMap(context or {})

    _, body = db_template(event)
    if body:
        try:
            return body.format_map(ctx)
        except Exception:
            logger.debug("notification_templates: DB body format failed for %s", event, exc_info=True)

    tpl = fallback_templates.get(event)
    if tpl:
        try:
            return tpl.format_map(ctx)
        except Exception:
            logger.debug("notification_templates: fallback format failed for %s", event, exc_info=True)

    order_ref = (context or {}).get("order_ref", "")
    return f"Notificacao: {event} — Pedido {order_ref}" if order_ref else f"Notificacao: {event}"
