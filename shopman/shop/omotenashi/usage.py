"""Omotenashi copy — mapa chave↔tela derivado do código (registro religado).

O problema que este módulo resolve: o operador vê um texto NA TELA e precisa
achar a chave certa no Admin ("mudei o título do cross-sell e não sabia onde").
A ponte é a VERDADE do código: onde cada chave registrada é consumida.

Duas metades:

- ``scan_usages()`` varre ``shopman/`` atrás de literais das chaves registradas
  (inclusive prefixos compostos em f-string, ex.: ``f"ORDER_STATUS_{...}"``) e
  devolve chave → arquivos consumidores. É I/O de filesystem — roda no comando
  ``omotenashi_usage_map`` e no teste de deriva, nunca em request.
- ``CONSUMER_SCREENS`` traduz cada arquivo consumidor em rótulo humano
  (superfície, tela). A curadoria é POR ARQUIVO (≈20, estáveis), não por chave
  (347). Arquivo sem rótulo cai em ("Outros", <path>) — o teste de deriva acusa.

O snapshot gerado vive em ``usage_map.py`` (checado no repo); o catálogo de
copy do Admin lê o snapshot (import puro, sem I/O).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Arquivos que NUNCA contam como consumo (registro, facades, gerados).
EXCLUDED_SUFFIXES = (
    "shop/omotenashi/copy.py",
    "shop/omotenashi/usage.py",
    "shop/omotenashi/usage_map.py",
    "shop/projections/copy.py",  # facade genérico (resolve_copy/title/message)
)

# Curadoria arquivo → (superfície, tela). O rótulo é o que o OPERADOR reconhece.
CONSUMER_SCREENS: dict[str, tuple[str, str]] = {
    "shopman/storefront/presentation/home.py": ("Loja", "Início"),
    "shopman/storefront/presentation/catalog.py": ("Loja", "Cardápio"),
    "shopman/storefront/presentation/product_detail.py": ("Loja", "Página do produto"),
    "shopman/storefront/presentation/cart.py": ("Loja", "Sacola"),
    "shopman/storefront/presentation/checkout.py": ("Loja", "Checkout"),
    "shopman/storefront/presentation/payment.py": ("Loja", "Pagamento"),
    "shopman/storefront/presentation/order_tracking.py": ("Loja", "Acompanhamento do pedido"),
    "shopman/storefront/presentation/reorder.py": ("Loja", "Pedir de novo"),
    "shopman/storefront/presentation/shop_status.py": ("Loja", "Status da loja"),
    "shopman/storefront/presentation/shop.py": ("Loja", "Institucional"),
    "shopman/storefront/presentation/status.py": ("Loja", "Rótulos de status"),
    "shopman/storefront/api/account.py": ("Loja", "Conta do cliente"),
    "shopman/storefront/api/auth.py": ("Loja", "Entrar"),
    "shopman/storefront/api/tracking.py": ("Loja", "Acompanhamento do pedido"),
    "shopman/storefront/api/payment.py": ("Loja", "Pagamento"),
    "shopman/storefront/api/confirmation.py": ("Loja", "Confirmação do pedido"),
    "shopman/storefront/api/surface.py": ("Loja", "Disponibilidade e avisos"),
    "shopman/storefront/api/views.py": ("Loja", "Superfície geral"),
    "shopman/shop/projections/order_tracking.py": ("Loja", "Acompanhamento do pedido"),
    "shopman/shop/projections/payment_status.py": ("Loja", "Pagamento"),
    "shopman/shop/modifiers.py": ("Loja", "Preços e promoções"),
    "shopman/backstage/presentation/status.py": ("Operador", "Rótulos de status"),
}

UNMAPPED_SURFACE = "Outros"


@dataclass(frozen=True)
class UsageRef:
    path: str  # relativo à raiz do repo
    surface: str
    screen: str


def screen_for(path: str) -> tuple[str, str]:
    return CONSUMER_SCREENS.get(path, (UNMAPPED_SURFACE, path))


def _registered_keys() -> list[str]:
    """Chaves do registry, lidas estaticamente (sem importar Django)."""
    source = (REPO_ROOT / "shopman/shop/omotenashi/copy.py").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'^    "([A-Z0-9_]+)": \{', source, re.M)))


def scan_usages() -> dict[str, tuple[UsageRef, ...]]:
    """Varre shopman/ e devolve chave → consumidores (ordenado, determinístico)."""
    keys = _registered_keys()
    literal = re.compile(r'["\'](' + "|".join(sorted(keys, key=len, reverse=True)) + r')["\']')
    # Prefixo composto: f"ORDER_STATUS_{...}" consome toda chave ORDER_STATUS_*.
    fstring_prefix = re.compile(r'f["\']([A-Z0-9_]+_)\{')

    by_key: dict[str, set[str]] = {key: set() for key in keys}
    for path in sorted((REPO_ROOT / "shopman").rglob("*.py")):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel or "/migrations/" in rel or rel.endswith(EXCLUDED_SUFFIXES):
            continue
        source = path.read_text(encoding="utf-8")
        for key in set(literal.findall(source)):
            by_key[key].add(rel)
        for prefix in set(fstring_prefix.findall(source)):
            for key in keys:
                if key.startswith(prefix):
                    by_key[key].add(rel)

    return {
        key: tuple(UsageRef(path, *screen_for(path)) for path in sorted(paths))
        for key, paths in by_key.items()
    }


def render_usage_map(usages: dict[str, tuple[UsageRef, ...]]) -> str:
    """Serializa o snapshot como módulo Python gerado (determinístico)."""
    lines = [
        '"""GERADO por `manage.py omotenashi_usage_map` — não edite à mão.',
        "",
        "Snapshot do mapa chave↔tela (ver usage.py). O teste de deriva compara",
        "este arquivo com o scan real e falha quando o consumo de copy muda.",
        '"""',
        "",
        "USAGE: dict[str, tuple[tuple[str, str, str], ...]] = {",
    ]
    for key in sorted(usages):
        refs = usages[key]
        if not refs:
            lines.append(f'    "{key}": (),')
            continue
        lines.append(f'    "{key}": (')
        for ref in refs:
            lines.append(f'        ("{ref.path}", "{ref.surface}", "{ref.screen}"),')
        lines.append("    ),")
    lines.append("}")
    lines.append("")
    return "\n".join(lines)


def load_usage_map() -> dict[str, tuple[UsageRef, ...]]:
    """Snapshot checado no repo (import puro — uso em request é barato)."""
    from .usage_map import USAGE

    return {
        key: tuple(UsageRef(*entry) for entry in entries)
        for key, entries in USAGE.items()
    }
