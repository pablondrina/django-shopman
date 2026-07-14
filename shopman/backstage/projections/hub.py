"""OperatorHubProjection — a Central de Apps (launcher pós-login).

Read model do "launcher" do operador: uma grade de tiles das superfícies de operador
(PDV · Cozinha · Gestor · Fournil · Loja), **permission-aware** — o app que o operador
não pode acessar nem aparece. É só um índice de navegação; não hospeda CRUD. O tile
Loja abre a **loja do cliente** (storefront) em nova aba — fora da zona de operador.

Registry declarativo (tipado aqui; caminho claro p/ configurável no Admin depois). Cada
tile carrega o predicado de permissão canônico de `backstage.permissions` — a mesma regra
que gateia a superfície dedicada e a sidebar. As URLs vêm de `settings.SHOPMAN_SURFACE_URLS`
(default de dev abaixo); em prod são os subdomínios (`pdv.`/`kds.`/`gestor.`/`prod.`) e o
apex da loja.

Nunca importa de `shopman.backstage.views.*`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings

from shopman.backstage.permissions import (
    can_access_production,
    can_manage_orders,
    can_operate_kds,
    can_operate_pos,
    is_superuser,
)

# URLs das superfícies — dev por padrão; sobrepostas por `settings.SHOPMAN_SURFACE_URLS`
# (env em prod: os subdomínios `.boulangerie` + o apex da loja).
DEFAULT_SURFACE_URLS: dict[str, str] = {
    "pos": "http://127.0.0.1:3002/",
    "kds": "http://127.0.0.1:3003/",
    "gestor": "http://127.0.0.1:3004/",
    "production": "http://127.0.0.1:3005/",
    "loja": "http://127.0.0.1:3000/",
}


@dataclass(frozen=True)
class HubTileProjection:
    """Um tile do launcher — uma superfície de operador que o usuário PODE abrir."""

    ref: str
    label: str
    description: str
    icon: str  # nome Lucide (ícone forte da superfície, DS §6)
    url: str
    kind: str  # "launch" (superfície de operador, mesma aba) | "external" (fora da zona, nova aba)


@dataclass(frozen=True)
class OperatorHubProjection:
    operator_name: str
    tiles: tuple[HubTileProjection, ...]


@dataclass(frozen=True)
class _AppSpec:
    ref: str
    label: str
    description: str
    icon: str
    kind: str
    can_access: Callable[[object], bool]


# Registro declarativo das superfícies (ordem = ordem de exibição). Ícone forte por
# app conforme o design system canônico (DS §6).
_REGISTRY: tuple[_AppSpec, ...] = (
    _AppSpec("pos", "PDV", "Vender no balcão", "banknote", "launch", can_operate_pos),
    _AppSpec("kds", "Cozinha", "Preparo e expedição", "chef-hat", "launch", can_operate_kds),
    _AppSpec("gestor", "Gestor de Pedidos", "Fila e acompanhamento", "clipboard-list", "launch", can_manage_orders),
    _AppSpec("production", "Fournil", "Produção e fornadas", "croissant", "launch", can_access_production),
    _AppSpec("loja", "Loja online", "Abrir a loja do cliente", "store", "external", is_superuser),
)


def _surface_urls() -> dict[str, str]:
    override = getattr(settings, "SHOPMAN_SURFACE_URLS", None) or {}
    return {**DEFAULT_SURFACE_URLS, **override}


def _operator_name(user) -> str:
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or getattr(user, "username", "") or "Operador"


def build_operator_hub(user) -> OperatorHubProjection:
    """Monta o launcher para `user`, contendo APENAS os tiles que ele pode acessar."""
    urls = _surface_urls()
    tiles = tuple(
        HubTileProjection(
            ref=spec.ref,
            label=spec.label,
            description=spec.description,
            icon=spec.icon,
            url=urls.get(spec.ref, "#"),
            kind=spec.kind,
        )
        for spec in _REGISTRY
        if spec.can_access(user)
    )
    return OperatorHubProjection(operator_name=_operator_name(user), tiles=tiles)
