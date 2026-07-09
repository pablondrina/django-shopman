"""Login por WhatsApp via access link (start leve).

O botão do site traz o cliente para o fluxo de access link do doorman: guardamos o
contexto ({cart_session_key, next}) sob um código ``NB-XxXx`` de uso único no cache e
devolvemos um deep link ``wa.me`` já preenchido. O cliente envia a mensagem; o ManyChat
casa o código e cria o access link (``AccessLinkCreateView``), que loga a sessão e adota
a sacola. A identidade é o número que ENVIA a mensagem (zero-telefone) — sem handshake,
sem bind de sessão, sem polling/SSE. Ver ACCESS-LINK-UNIFICATION-PLAN.md.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

from django.conf import settings

logger = logging.getLogger(__name__)


def _config() -> dict:
    return getattr(settings, "SHOPMAN_WA_VERIFY", {}) or {}


def _wa_number() -> str:
    """Número (só dígitos, E.164 sem '+') do WhatsApp da loja para o deep link."""
    num = re.sub(r"\D", "", str(_config().get("number") or ""))
    if num:
        return num
    try:
        from shopman.shop.models import Shop

        shop = Shop.objects.first()
        if shop and getattr(shop, "phone", ""):
            return re.sub(r"\D", "", shop.phone)
    except Exception:
        logger.debug("wa_verify: fallback para Shop.phone degradado", exc_info=True)
    return ""


def _safe_next(raw: str) -> str:
    """Destino pós-login. Só caminhos internos (guard de open-redirect): começa com
    '/' e não '//' (protocol-relative). Caso contrário, vazio."""
    value = (raw or "").strip()
    if value.startswith("/") and not value.startswith("//"):
        return value
    return ""


def _access_message_text(code: str) -> str:
    """Mensagem pré-preenchida do botão do site. O código NB-XxXx é a parte que o
    ManyChat casa (gatilho/regex); o texto ao redor é configurável e cosmético."""
    template = str(_config().get("access_message_template") or "Meu código de acesso é {code}")
    try:
        return template.format(code=code)
    except (KeyError, IndexError, ValueError):
        return code


def _access_deep_link(code: str) -> str:
    number = _wa_number()
    query = urllib.parse.quote(_access_message_text(code))
    if number:
        return f"https://wa.me/{number}?text={query}"
    return f"https://wa.me/?text={query}"


def start_access_link(*, cart_session_key: str = "", next_path: str = "") -> dict:
    """Guarda o contexto do site ({cart_session_key, next}) sob um código NB-XxXx
    (uso único, no cache) e devolve o deep link com o código pré-preenchido.

    Sem token de handshake, sem bind de sessão, sem polling/SSE: a identidade é o
    número que envia a mensagem no WhatsApp; o código só carrega contexto (destino
    + sacola), consumido na criação do access link (``AccessLinkCreateView``).
    """
    from shopman.doorman.services.link_state import store_state

    state: dict = {}
    if cart_session_key:
        state["cart_session_key"] = str(cart_session_key)
    safe_next = _safe_next(next_path)
    if safe_next:
        state["next"] = safe_next

    code = store_state(state)
    logger.info(
        "wa_access.start code_issued has_cart=%s has_next=%s",
        bool(cart_session_key),
        bool(safe_next),
    )
    return {"code": code, "deep_link": _access_deep_link(code), "wa_number": _wa_number()}
