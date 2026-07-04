"""Fonte única dos links da LOJA (superfície Nuxt) gerados pelo Django.

Arquitetura desacoplada: a loja de cliente é o Nuxt; o Django é **headless** —
nunca serve páginas de cliente, mas GERA links de cliente (notificações de
pagamento/acompanhamento, magic links, "ver site" no admin). Todos esses links
são construídos aqui, atrás de uma única base configurável
(`settings.SHOPMAN_STOREFRONT_BASE_URL`).

Cutover de domínio é um único knob: em produção, aponte
`SHOPMAN_STOREFRONT_BASE_URL=https://nelson.com` e todos os links de cliente
passam a apontar para o apex — sem caçar caminho por caminho.

Os caminhos abaixo são os caminhos CANÔNICOS da loja Nuxt (não os antigos do
Django legado). Mantenha-os em sincronia com `surfaces/storefront-nuxt`.
"""
from __future__ import annotations

from django.conf import settings


def storefront_base_url() -> str:
    """Base absoluta da loja (sem trailing slash). Vazio ⇒ links relativos."""
    return (getattr(settings, "SHOPMAN_STOREFRONT_BASE_URL", "") or "").rstrip("/")


# ── Caminhos canônicos da loja Nuxt (relativos) ──────────────────────
def path_home() -> str:
    return "/"


def path_menu() -> str:
    return "/menu"


def path_product(sku: str) -> str:
    return f"/product/{sku}"


def path_cart() -> str:
    return "/cart"


def path_checkout() -> str:
    return "/checkout"


def path_order_tracking(ref: str) -> str:
    return f"/tracking/{ref}"


def path_order_payment(ref: str) -> str:
    return f"/pedido/{ref}/pagamento"


def path_account() -> str:
    return "/account"


def path_order_history() -> str:
    return "/account/pedidos"


def path_login() -> str:
    return "/login"


def path_access() -> str:
    """Magic-link bridge route on the Nuxt store (`/a?t=<token>`).

    The page exchanges the token via the BFF (`/api/auth/access/`), so the
    session cookie is set on the store host, then navigates to the destination
    the backend derives from the token metadata.
    """
    return "/a"


def storefront_url(path: str) -> str:
    """URL absoluta da loja para um caminho (base + caminho).

    Se a base não estiver configurada, retorna o caminho relativo — útil em dev e
    quando o consumidor resolve o domínio por conta própria.
    """
    if not path.startswith("/"):
        path = f"/{path}"
    base = storefront_base_url()
    return f"{base}{path}" if base else path


# ── Atalhos absolutos (o que os geradores de link de cliente consomem) ─
def order_tracking_url(ref: str) -> str:
    return storefront_url(path_order_tracking(ref))


def order_payment_url(ref: str) -> str:
    return storefront_url(path_order_payment(ref))


def product_url(sku: str) -> str:
    return storefront_url(path_product(sku))


def home_url() -> str:
    return storefront_url(path_home())


def cart_url() -> str:
    return storefront_url(path_cart())


def account_url() -> str:
    return storefront_url(path_account())
