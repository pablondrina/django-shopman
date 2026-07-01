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


def _edit_url(product) -> str:
    """Deep-link canônico p/ a edição do produto no Admin/Unfold."""
    from django.urls import NoReverseMatch, reverse

    try:
        return reverse(
            f"admin:{product._meta.app_label}_{product._meta.model_name}_change",
            args=[product.pk],
        )
    except NoReverseMatch:
        return ""


@dataclass(frozen=True)
class SurfaceProjection:
    """Um canal (de venda) — coluna da matriz."""

    ref: str
    name: str
    is_projection_target: bool  # tem backend na registry canônica (Frente 1) — ex.: iFood
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
    edit_url: str  # deep-link p/ a página de edição do produto (Admin/Unfold)
    # estoque (produto-level, do loop produção→estoque→disponibilidade). Esgotado é
    # ortogonal a Pausado: não mexe no switch; a próxima fornada repõe sozinho.
    stock_tracked: bool  # há controle de estoque para este SKU?
    stock_qty: int | None  # promissível agora (None = sem controle)
    sold_out: bool  # rastreado e sem estoque para vender
    low_stock: bool  # rastreado, pouco estoque (≤ threshold do canal)
    replenish_qty: int  # vindo por produção (planejado + em produção) — "fornada"
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


_EMPTY_STOCK = {
    "stock_tracked": False,
    "stock_qty": None,
    "sold_out": False,
    "low_stock": False,
    "replenish_qty": 0,
}


def _stock_view(info: dict | None, low_stock_threshold: int) -> dict:
    """Deriva o estado de estoque da linha a partir do dict canônico de availability.

    Esgotado = rastreado e sem promissível (nem físico nem fornada, conforme a
    política). ``replenish_qty`` = o que vem por produção (planejado + em produção).
    """
    if not info or not info.get("is_tracked", True):
        return dict(_EMPTY_STOCK)
    promisable = int(info.get("total_promisable") or 0)
    planned = int(info.get("planned") or 0)
    in_production = int((info.get("breakdown") or {}).get("in_production") or 0)
    sold_out = promisable <= 0
    return {
        "stock_tracked": True,
        "stock_qty": promisable,
        "sold_out": sold_out,
        "low_stock": (not sold_out) and promisable <= max(int(low_stock_threshold or 0), 0),
        "replenish_qty": max(planned + in_production, 0),
    }


def _stock_for(skus: list[str]) -> tuple[dict[str, dict | None], int]:
    """Availability em lote (canal representante) + threshold de estoque baixo.

    Estoque é físico/produto-level; usa o scope de UM canal representante (o de menor
    ``display_order``). Diferenças de scope entre canais (D-1) são de borda pro Gestor.
    Degrada em silêncio (sem Stockman → dict vazio → tudo untracked → como hoje).
    """
    from shopman.shop.config import ChannelConfig
    from shopman.shop.models import Channel

    rep = Channel.objects.filter(is_active=True).order_by("display_order", "id").first()
    if rep is None or not skus:
        return {}, 0
    threshold = int(getattr(ChannelConfig.for_channel(rep).stock, "low_stock_threshold", 0) or 0)

    from shopman.shop.projections import catalog_context

    return catalog_context.availability_for_skus(skus, channel_ref=rep.ref), threshold


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
        is_target = get_projection_backend(ch.ref) is not None
        surfaces.append(
            SurfaceProjection(
                ref=ch.ref,
                name=ch.name or ch.ref,
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

    products = list(products)
    stock_by_sku, low_stock_threshold = _stock_for([p.sku for p in products])

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

        stock = _stock_view(stock_by_sku.get(product.sku), low_stock_threshold)
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
                edit_url=_edit_url(product),
                stock_tracked=stock["stock_tracked"],
                stock_qty=stock["stock_qty"],
                sold_out=stock["sold_out"],
                low_stock=stock["low_stock"],
                replenish_qty=stock["replenish_qty"],
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
