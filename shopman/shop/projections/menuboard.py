"""
Menuboard projection — a superfície DISPLAY (quadro-negro) alimentada por coleção.

Um menuboard é um Channel com ``capability == "display"`` e ``content.source ==
"collection"``: mostra o recorte do catálogo daquela coleção (manual ou por regra),
com preço e disponibilidade, agrupado por coleção primária. Dado público (é um
cardápio numa TV) — sem estado de operador.

Preço/disponibilidade vêm do ListingItem da superfície quando existe (após
materializar); senão caem no nível do produto (base_price_q). Itens indisponíveis
não somem — aparecem como "Esgotado" (honestidade/omotenashi).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class MenuboardItem:
    sku: str
    name: str
    price_q: int  # centavos — a superfície formata (appearance fica na apresentação)
    available: bool
    description: str


@dataclass(frozen=True)
class MenuboardGroup:
    title: str
    items: tuple[MenuboardItem, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class MenuboardProjection:
    surface_ref: str
    title: str
    subtitle: str
    groups: tuple[MenuboardGroup, ...] = field(default_factory=tuple)
    available_count: int = 0
    is_display: bool = True


class MenuboardError(Exception):
    """Raised when a surface is not a valid menuboard (display + collection-fed)."""


def resolve_menuboard_config(surface_ref: str):
    """Valida que a superfície é um menuboard e devolve (channel, collection_ref)."""
    from shopman.shop.config import ChannelConfig
    from shopman.shop.models import Channel

    channel = Channel.objects.filter(ref=surface_ref, is_active=True).first()
    if channel is None:
        raise MenuboardError(f"Superfície '{surface_ref}' não encontrada ou inativa.")
    cfg = ChannelConfig.for_channel(channel)
    if cfg.capability != "display":
        raise MenuboardError(f"Superfície '{surface_ref}' não é um menuboard (capability != display).")
    if cfg.content.source != "collection" or not cfg.content.collection:
        raise MenuboardError(f"Menuboard '{surface_ref}' não tem coleção-fonte (content.collection).")
    return channel, cfg.content.collection


def build_menuboard(surface_ref: str) -> MenuboardProjection:
    """Monta o quadro do menuboard a partir da coleção-fonte da superfície."""
    from shopman.offerman.models import Collection, ListingItem

    channel, collection_ref = resolve_menuboard_config(surface_ref)
    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise MenuboardError(f"Coleção-fonte '{collection_ref}' não encontrada.")

    products = list(
        coll.product_queryset().prefetch_related("collection_items__collection")
    )

    # Overrides da superfície (preço/disponibilidade por item), quando materializado.
    items_by_sku = {
        item.product.sku: item
        for item in ListingItem.objects.filter(listing__ref=surface_ref).select_related("product")
    }

    # Agrupa por coleção primária (dá seções naturais: "Pães", "Doces"…).
    groups: dict[str, list[MenuboardItem]] = {}
    order: list[str] = []
    available_count = 0
    for product in sorted(products, key=lambda p: p.name):
        item = items_by_sku.get(product.sku)
        price_q = item.price_q if item is not None else product.base_price_q
        available = product.is_published and product.is_sellable
        if item is not None:
            available = available and item.is_published and item.is_sellable
        if available:
            available_count += 1

        primary = next((ci for ci in product.collection_items.all() if ci.is_primary), None)
        section = primary.collection.name if primary else coll.name
        if section not in groups:
            groups[section] = []
            order.append(section)
        groups[section].append(
            MenuboardItem(
                sku=product.sku,
                name=product.name,
                price_q=price_q,
                available=available,
                description=product.short_description or "",
            )
        )

    return MenuboardProjection(
        surface_ref=surface_ref,
        title=channel.name or coll.name,
        subtitle=coll.name,
        groups=tuple(MenuboardGroup(title=s, items=tuple(groups[s])) for s in order),
        available_count=available_count,
    )
