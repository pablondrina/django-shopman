"""
Catalog matrix projection — produto × superfície para o Gestor.

Cada superfície é um Channel (capacidade + fonte de conteúdo resolvidas do
ChannelConfig); cada célula (produto × superfície) reflete o ListingItem daquela
listing (convenção listing.ref == channel.ref). Estado por célula = produto-level
AND listing-level (ambos precisam concordar para o item estar disponível).

Read-only. Frozen dataclasses convertidos por ``backstage.api.projections.projection_data``.
"""

from __future__ import annotations

from dataclasses import dataclass

from shopman.utils.monetary import format_money


def _money(value_q: int) -> str:
    return f"R$ {format_money(int(value_q))}"


@dataclass(frozen=True)
class SurfaceProjection:
    """Uma superfície (canal) — coluna da matriz."""

    ref: str
    name: str
    capability: str  # transactional | display | feed
    content_source: str  # ref da coleção-fonte, ou "" (ListingItems explícitos)
    is_projection_target: bool  # tem backend na registry canônica (Frente 1)
    sync_status: str  # ok | error | never | na


@dataclass(frozen=True)
class SurfaceCellProjection:
    """Célula produto × superfície."""

    surface_ref: str
    in_listing: bool  # o produto está nesta listing?
    is_published: bool  # listing-level
    is_sellable: bool  # listing-level
    available: bool  # produto-level AND listing-level
    price_q: int | None
    price_display: str


@dataclass(frozen=True)
class CatalogRowProjection:
    """Uma linha da matriz — um produto e suas células por superfície."""

    sku: str
    name: str
    image_url: str
    primary_collection: str  # ref
    primary_collection_name: str
    is_published: bool  # produto-level
    is_sellable: bool  # produto-level
    base_price_q: int
    base_price_display: str
    keywords: tuple[str, ...]
    cells: tuple[SurfaceCellProjection, ...]  # alinhado à ordem de ``surfaces``


@dataclass(frozen=True)
class CollectionProjection:
    """Coleção — alça do eixo coleção (filtro/agrupamento/bulk)."""

    ref: str
    name: str
    is_smart: bool
    product_count: int


@dataclass(frozen=True)
class CatalogMatrixProjection:
    surfaces: tuple[SurfaceProjection, ...]
    rows: tuple[CatalogRowProjection, ...]
    collections: tuple[CollectionProjection, ...]


# ── builders ────────────────────────────────────────────────────────────────


def _surface_sync_status(listing, is_projection_target: bool) -> str:
    if not is_projection_target:
        return "na"
    meta = listing.projection_metadata if listing else {}
    if meta.get("last_error"):
        return "error"
    if meta.get("last_projected_skus"):
        return "ok"
    return "never"


def _build_surfaces() -> tuple[list[SurfaceProjection], dict[str, dict]]:
    """Retorna as superfícies + um índice {surface_ref: {sku: ListingItem}}."""
    from shopman.offerman.conf import get_projection_backend
    from shopman.offerman.models import Listing, ListingItem

    from shopman.shop.config import ChannelConfig
    from shopman.shop.models import Channel

    channels = list(Channel.objects.filter(is_active=True).order_by("display_order", "id"))
    listings = {lst.ref: lst for lst in Listing.objects.all()}

    # índice de células: surface_ref → sku → ListingItem (tier base = menor min_qty)
    cells_index: dict[str, dict] = {}
    items = (
        ListingItem.objects.filter(listing__ref__in=[c.ref for c in channels])
        .select_related("product", "listing")
        .order_by("product__sku", "min_qty")
    )
    for item in items:
        bucket = cells_index.setdefault(item.listing.ref, {})
        bucket.setdefault(item.product.sku, item)  # primeiro = menor min_qty

    surfaces: list[SurfaceProjection] = []
    for ch in channels:
        cfg = ChannelConfig.for_channel(ch)
        is_target = get_projection_backend(ch.ref) is not None
        surfaces.append(
            SurfaceProjection(
                ref=ch.ref,
                name=ch.name or ch.ref,
                capability=cfg.capability,
                content_source=cfg.content.collection or "",
                is_projection_target=is_target,
                sync_status=_surface_sync_status(listings.get(ch.ref), is_target),
            )
        )
    return surfaces, cells_index


def build_catalog_matrix(collection_ref: str = "") -> CatalogMatrixProjection:
    """Monta a matriz produto × superfície com o eixo coleção.

    ``collection_ref`` (opcional) filtra as linhas aos produtos daquela coleção,
    resolvida por ``product_queryset()`` (smart-aware) — funciona para coleções
    manuais e por regra.
    """
    from shopman.offerman.models import Collection, Product

    surfaces, cells_index = _build_surfaces()

    products = (
        Product.objects.all()
        .order_by("name")
        .prefetch_related("keywords", "collection_items__collection")
    )
    if collection_ref:
        coll = Collection.objects.filter(ref=collection_ref).first()
        products = products.filter(pk__in=coll.product_queryset().values("pk")) if coll else products.none()

    rows: list[CatalogRowProjection] = []
    for product in products:
        primary_ref = ""
        primary_name = ""
        primary = next((ci for ci in product.collection_items.all() if ci.is_primary), None)
        if primary:
            primary_ref = primary.collection.ref
            primary_name = primary.collection.name

        cells: list[SurfaceCellProjection] = []
        for surface in surfaces:
            item = cells_index.get(surface.ref, {}).get(product.sku)
            if item is None:
                cells.append(
                    SurfaceCellProjection(
                        surface_ref=surface.ref,
                        in_listing=False,
                        is_published=False,
                        is_sellable=False,
                        available=False,
                        price_q=None,
                        price_display="",
                    )
                )
                continue
            available = (
                product.is_published and product.is_sellable and item.is_published and item.is_sellable
            )
            cells.append(
                SurfaceCellProjection(
                    surface_ref=surface.ref,
                    in_listing=True,
                    is_published=item.is_published,
                    is_sellable=item.is_sellable,
                    available=available,
                    price_q=item.price_q,
                    price_display=_money(item.price_q),
                )
            )

        rows.append(
            CatalogRowProjection(
                sku=product.sku,
                name=product.name,
                image_url=product.image_url or "",
                primary_collection=primary_ref,
                primary_collection_name=primary_name,
                is_published=product.is_published,
                is_sellable=product.is_sellable,
                base_price_q=product.base_price_q,
                base_price_display=_money(product.base_price_q),
                keywords=tuple(product.keywords.names()),
                cells=tuple(cells),
            )
        )

    collections = tuple(
        CollectionProjection(
            ref=c.ref,
            name=c.name,
            is_smart=c.is_smart,
            product_count=c.product_queryset().count(),
        )
        for c in Collection.objects.filter(is_active=True).order_by("sort_order", "name")
    )

    return CatalogMatrixProjection(surfaces=tuple(surfaces), rows=tuple(rows), collections=collections)
