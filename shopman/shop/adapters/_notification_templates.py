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


def render_template(tpl: str, context: dict) -> str:
    """Renderiza um template com SafeFormatMap, degradando ao template cru.

    ``str.format_map`` levanta ValueError/IndexError em chave malformada
    (chave solta, ``{0}`` posicional, spec inválido) — e SafeFormatMap só
    resgata chave AUSENTE. Um typo do lojista num assunto/corpo do Admin não
    pode suprimir a mensagem inteira; melhor o template cru que silêncio.
    """
    try:
        return tpl.format_map(SafeFormatMap(context or {}))
    except Exception:
        logger.debug("notification_templates: template render failed, using raw", exc_info=True)
        return tpl


def render_message(event: str, context: dict, fallback_templates: dict[str, str]) -> str:
    """Corpo da mensagem: Admin (DB) → fallback hardcoded do canal → genérico."""
    _, body = db_template(event)
    if body:
        return render_template(body, context)

    tpl = fallback_templates.get(event)
    if tpl:
        return render_template(tpl, context)

    order_ref = (context or {}).get("order_ref", "")
    return f"Notificacao: {event} — Pedido {order_ref}" if order_ref else f"Notificacao: {event}"
