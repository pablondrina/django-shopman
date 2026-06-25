"""Fonte única dos links das superfícies de OPERADOR (Nuxt) geradas pelo Django.

As superfícies operacionais migraram para apps Nuxt dedicados, cada um no seu
subdomínio, conversando com o Django via ``api/v1/backstage/*``:

  · Gestor de Pedidos → ``surfaces/orders-uithing-nuxt``      (``gestor.``)
  · KDS               → ``surfaces/kds-uithing-nuxt``          (``kds.``)
  · Produção          → ``surfaces/production-uithing-nuxt``    (``fournil.``)

Como a loja do cliente e o POS, o Django só APONTA para esses apps, atrás de uma
única base configurável por deployment (``settings.SHOPMAN_*_BASE_URL``). Quando a
base está vazia, o app não está conectado neste contexto (por exemplo, o gate
Omotenashi storefront não sobe os apps de operador): o builder retorna "" e o
chamador trata como "pular" — nunca apontar para uma rota Django morta.

Espelha ``pos_links``/``storefront_links``. Mantenha os caminhos em sincronia com
as surfaces correspondentes.
"""
from __future__ import annotations

from django.conf import settings


def _base(setting_name: str) -> str:
    return (getattr(settings, setting_name, "") or "").rstrip("/")


def _url(base: str, path: str) -> str:
    if not base:
        return ""
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


# ── Gestor de Pedidos (orders-uithing-nuxt) ────────────────────────────────


def orders_base_url() -> str:
    return _base("SHOPMAN_ORDERS_BASE_URL")


def orders_url(path: str = "/") -> str:
    """URL absoluta do Gestor de Pedidos, ou "" quando não está conectado."""
    return _url(orders_base_url(), path)


# ── KDS (kds-uithing-nuxt) ─────────────────────────────────────────────────


def kds_base_url() -> str:
    return _base("SHOPMAN_KDS_BASE_URL")


def kds_url(path: str = "/") -> str:
    """URL absoluta do KDS, ou "" quando não está conectado."""
    return _url(kds_base_url(), path)


# ── Produção (production-uithing-nuxt) ──────────────────────────────────────


def production_base_url() -> str:
    return _base("SHOPMAN_PRODUCTION_BASE_URL")


def production_url(path: str = "/") -> str:
    """URL absoluta da Produção (chão ao vivo), ou "" quando não está conectada."""
    return _url(production_base_url(), path)
