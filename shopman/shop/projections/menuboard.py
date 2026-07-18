"""
Menuboard projection — o 📺 Feed de tipo ``menuboard`` numa TV.

Um Feed (``shop.Showcase``) compõe N coleções; no menuboard cada coleção é uma
SEÇÃO (Pães, Doces, Bebidas…). Mostra o estado CANÔNICO do produto (base_price +
is_published/is_sellable) — pausar o produto tira do quadro. Dado público (é um
cardápio numa TV) — sem estado de operador, sem override por-superfície.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MenuboardItem:
    sku: str
    name: str
    price_q: int  # centavos — a superfície formata (appearance na apresentação)
    available: bool
    description: str


@dataclass(frozen=True)
class MenuboardGroup:
    title: str
    items: tuple[MenuboardItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MenuboardProjection:
    ref: str
    title: str
    subtitle: str
    groups: tuple[MenuboardGroup, ...] = field(default_factory=tuple)
    available_count: int = 0
    is_display: bool = True


class MenuboardError(Exception):
    """Raised when a ref is not a valid, active menuboard Showcase."""


def resolve_menuboard(ref: str):
    """Valida que ``ref`` é um Feed menuboard ativo e o devolve."""
    from shopman.shop.models import Showcase

    sc = Showcase.objects.filter(ref=ref, is_active=True, kind=Showcase.KIND_MENUBOARD).first()
    if sc is None:
        raise MenuboardError(f"Menuboard '{ref}' não encontrado ou inativo.")
    return sc


def build_menuboard(ref: str) -> MenuboardProjection:
    """Monta o quadro: uma seção por coleção do feed, na ordem das coleções."""
    from shopman.offerman.models import Collection

    showcase = resolve_menuboard(ref)
    # Coleções na ordem do feed; ordenação de exibição = sort_order da coleção.
    colls = {c.ref: c for c in Collection.objects.filter(ref__in=showcase.collection_refs())}
    paused = showcase.paused_skus()  # pausa LOCAL do feed (a global é do produto)

    groups: list[MenuboardGroup] = []
    available_count = 0
    for coll_ref in showcase.collection_refs():
        coll = colls.get(coll_ref)
        if coll is None:
            continue
        items: list[MenuboardItem] = []
        for product in coll.product_queryset().order_by("name"):
            available = product.is_published and product.is_sellable and product.sku not in paused
            if available:
                available_count += 1
            items.append(
                MenuboardItem(
                    sku=product.sku,
                    name=product.name,
                    price_q=product.base_price_q,
                    available=available,
                    description=product.short_description or "",
                )
            )
        if items:
            groups.append(MenuboardGroup(title=coll.name, items=tuple(items)))

    return MenuboardProjection(
        ref=ref,
        title=showcase.name,
        subtitle="",
        groups=tuple(groups),
        available_count=available_count,
    )
