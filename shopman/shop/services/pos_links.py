"""Fonte única dos links da superfície POS (operador) gerados pelo Django.

O PDV migrou para o seu próprio app Nuxt (`surfaces/pos-nuxt`), que
conversa com o Django via `api/v1/backstage/pos/*`. Como a loja do cliente, o
Django só APONTA para o POS, atrás de uma única base configurável
(`settings.SHOPMAN_POS_BASE_URL`).

Quando a base está vazia, o POS não está conectado neste contexto (por exemplo, o
gate Omotenashi storefront+operador não sobe o POS): `pos_url()` retorna "" e o
chamador trata isso como "pular" — nunca apontar para a rota Django morta que o
PDV deixou para trás.

Espelha `storefront_links` (loja do cliente). Mantenha os caminhos em sincronia
com `surfaces/pos-nuxt`.
"""
from __future__ import annotations

from django.conf import settings


def pos_base_url() -> str:
    """Base absoluta do POS (sem trailing slash). Vazio ⇒ POS não conectado."""
    return (getattr(settings, "SHOPMAN_POS_BASE_URL", "") or "").rstrip("/")


def path_counter() -> str:
    """Tela de venda do PDV (rota raiz)."""
    return "/"


def path_session() -> str:
    """Antesala de sessão de caixa (abrir/fechar turno, movimentos)."""
    return "/session"


def path_day_closing() -> str:
    """Fechamento do DIA (contagem cega de sobras/perdas) na antesala."""
    return "/session/closing"


def pos_url(path: str) -> str:
    """URL absoluta do POS para um caminho, ou "" quando o POS não está conectado."""
    base = pos_base_url()
    if not base:
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"
