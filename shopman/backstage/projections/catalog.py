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
    """Uma superfície — coluna da matriz. Canal (transaciona) ou Feed (só exibe)."""

    ref: str
    name: str
    # Rótulo curto do cabeçalho da coluna (a matriz é estreita). Nunca vazio: cai
    # para `name` quando não há um curto configurado. O `name` completo segue no
    # tooltip da coluna e em toda lista onde há espaço.
    short_name: str
    is_projection_target: bool  # tem backend na registry canônica (Frente 1) — ex.: iFood
    sync_status: str  # ok | error | never | na
    kind: str = "channel"  # channel (transacional) | display (menuboard) | feed (Google/Meta)
    transactional: bool = True  # canal vende (preço/publicação); feed só exibe (pausa)
    icon: str = ""  # dica de ícone p/ feeds (tv/rss)
    is_active: bool = True  # feed ligado/desligado (canal sempre ativo aqui)
    output_path: str = ""  # saída pública do feed (abrir/prever); vazio p/ canal
    sync_key: str = ""  # chave no CatalogSyncState.platform (ref p/ canais, kind p/ showcases)


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
    # Estado de sync por (produto × plataforma) — CatalogSyncState (Arc C). Só faz
    # sentido em superfície que é alvo de projeção (canal com backend na registry);
    # vazio quando nunca houve push ou a superfície não projeta (feed de pull).
    sync_status: str = ""  # synced | pending | error | retracted | skipped | "" (nunca)
    sync_error: str = ""  # última mensagem de erro (quando status=error)
    synced_at: str = ""  # ISO do último push OK (synced/retracted)


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
    # PIM social (Arc A) — atributos de catálogo social em Product.metadata['social'],
    # lidos por get_social_attributes. Alimentam o painel PIM e sinalizam prontidão de
    # feed (Google/Meta/TikTok exigem brand + categoria). Ver ``_social_view``.
    social: dict
    pim_complete: bool  # tem o essencial p/ publicar em feed (brand + categoria Google)


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


def _stock_view(info: dict | None, low_stock_threshold: int, replenish_qty: int) -> dict:
    """Deriva o estado de estoque da linha a partir do dict canônico de availability.

    Esgotado = rastreado e sem promissível AGORA. ``replenish_qty`` vem de uma consulta
    SEPARADA (fornadas futuras) — não do promissível-agora — pra não mascarar o esgotado.
    """
    if not info or not info.get("is_tracked", True):
        return {**_EMPTY_STOCK, "replenish_qty": max(int(replenish_qty or 0), 0)}
    promisable = int(info.get("total_promisable") or 0)
    sold_out = promisable <= 0
    return {
        "stock_tracked": True,
        "stock_qty": promisable,
        "sold_out": sold_out,
        "low_stock": (not sold_out) and promisable <= max(int(low_stock_threshold or 0), 0),
        "replenish_qty": max(int(replenish_qty or 0), 0),
    }


def _stock_for(skus: list[str]) -> tuple[dict[str, dict | None], int, dict[str, int]]:
    """Availability-agora (canal representante) + threshold + suprimento planejado.

    Estoque é físico/produto-level; usa o scope de UM canal representante (o de menor
    ``display_order``). ``planned`` é uma consulta separada (fornadas futuras próximas).
    Degrada em silêncio (sem Stockman → vazio → tudo untracked → como hoje).
    """
    from shopman.shop.config import ChannelConfig
    from shopman.shop.models import Channel

    rep = Channel.objects.filter(is_active=True).order_by("display_order", "id").first()
    if rep is None or not skus:
        return {}, 0, {}
    threshold = int(getattr(ChannelConfig.for_channel(rep).stock, "low_stock_threshold", 0) or 0)

    from shopman.shop.projections import catalog_context

    availability = catalog_context.availability_for_skus(skus, channel_ref=rep.ref)
    planned = catalog_context.planned_supply_for_skus(skus)
    return availability, threshold, planned


def _social_view(product) -> tuple[dict, bool]:
    """Atributos PIM sociais da linha + prontidão de feed.

    ``pim_complete`` = tem o mínimo p/ um feed comercial (Google/Meta/TikTok): marca
    e categoria Google. GTIN/condição são refinamentos, não bloqueiam o sinal verde.
    """
    from shopman.offerman.contrib.social.schema import get_social_attributes

    attrs = get_social_attributes(product)
    view = {
        "brand": attrs.brand,
        "gtin": attrs.gtin,
        "mpn": attrs.mpn,
        "condition": attrs.condition,
        "google_product_category": attrs.google_product_category,
        "tiktok_category_id": attrs.tiktok_category_id,
        "hashtags": list(attrs.hashtags),
        "social_caption": attrs.social_caption,
        "has_data": attrs.has_data,
    }
    complete = bool(attrs.brand and attrs.google_product_category)
    return view, complete


def _cell_sync(sync_map: dict, sku: str, surface_ref: str) -> tuple[str, str, str]:
    """(status, error, synced_at) do CatalogSyncState p/ (sku, surface_ref) — ou vazios."""
    rec = sync_map.get(sku, {}).get(surface_ref)
    if not rec:
        return "", "", ""
    return rec.get("status") or "", rec.get("error") or "", rec.get("last_synced_at") or ""


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
        # `short_name` é chave de ChannelConfig, lida direto do override do canal:
        # é presentação POR canal (não há default de loja que faça sentido), e assim
        # evitamos um Shop.load() por canal só para resolver a cascata.
        short = str((ch.config or {}).get("short_name", "")).strip()
        surfaces.append(
            SurfaceProjection(
                ref=ch.ref,
                name=ch.name or ch.ref,
                short_name=short or ch.name or ch.ref,
                is_projection_target=is_target,
                sync_status=_surface_sync_status(listings.get(ch.ref), is_target),
                kind="channel",
                transactional=True,
                sync_key=ch.ref,
            )
        )
    return surfaces, cells_index


# capability/ícone por tipo de feed (espelha backstage.projections.showcase)
_SHOWCASE_META = {
    "menuboard": {"capability": "display", "icon": "tv", "path": "/menuboard/{ref}/"},
    "google": {"capability": "feed", "icon": "rss", "path": "/feed/{ref}.xml"},
    "meta": {"capability": "feed", "icon": "rss", "path": "/feed/{ref}.xml?platform=meta"},
}


def _build_showcase_surfaces() -> tuple[list[SurfaceProjection], dict[str, dict]]:
    """Feeds como colunas + índice {ref: {"members": set, "paused": set}}.

    ``members`` = SKUs presentes no feed (união dos produtos das suas coleções).
    ``paused`` = pausa LOCAL do item no feed (a global é do produto, gate por cima).
    """
    from shopman.offerman.conf import get_projection_backend
    from shopman.offerman.models import Collection

    from shopman.shop.models import Showcase

    showcases = list(Showcase.objects.all().order_by("name"))
    if not showcases:
        return [], {}

    # resolve os SKUs de cada coleção uma única vez (reuso entre feeds)
    needed_refs = {r for sc in showcases for r in sc.collection_refs()}
    members_by_coll: dict[str, set[str]] = {}
    for coll in Collection.objects.filter(ref__in=needed_refs):
        members_by_coll[coll.ref] = set(coll.product_queryset().values_list("sku", flat=True))

    surfaces: list[SurfaceProjection] = []
    index: dict[str, dict] = {}
    for sc in showcases:
        meta = _SHOWCASE_META.get(sc.kind, {"capability": "display", "icon": "monitor", "path": ""})
        members: set[str] = set()
        for r in sc.collection_refs():
            members |= members_by_coll.get(r, set())
        index[sc.ref] = {"members": members, "paused": sc.paused_skus()}
        # Showcase projection backends are keyed by kind (e.g. "meta", "google").
        is_target = get_projection_backend(sc.kind) is not None
        short = str((sc.options or {}).get("short_name", "")).strip()
        surfaces.append(
            SurfaceProjection(
                ref=sc.ref,
                name=sc.name or sc.ref,
                short_name=short or sc.name or sc.ref,
                is_projection_target=is_target,
                sync_status=_surface_sync_status(None, is_target),
                sync_key=sc.kind,
                kind=meta["capability"],
                transactional=False,
                icon=meta["icon"],
                is_active=sc.is_active,
                output_path=meta["path"].format(ref=sc.ref),
            )
        )
    return surfaces, index


def build_catalog_matrix(collection_ref: str = "") -> CatalogMatrixProjection:
    """Monta a matriz produto × superfície com o eixo coleção.

    ``collection_ref`` (opcional) filtra as linhas aos produtos daquela coleção,
    resolvida por ``product_queryset()`` (smart-aware) — funciona para coleções
    manuais e por regra.
    """
    from shopman.offerman.models import Collection, Product

    surfaces, cells_index = _build_surfaces()
    showcase_surfaces, showcase_index = _build_showcase_surfaces()
    surfaces = surfaces + showcase_surfaces

    products = (
        Product.objects.all()
        .order_by("name")
        .prefetch_related("keywords", "collection_items__collection")
    )
    if collection_ref:
        coll = Collection.objects.filter(ref=collection_ref).first()
        products = products.filter(pk__in=coll.product_queryset().values("pk")) if coll else products.none()

    products = list(products)
    skus = [p.sku for p in products]
    stock_by_sku, low_stock_threshold, planned_by_sku = _stock_for(skus)

    # Estado de sync por (produto × plataforma) — uma consulta p/ toda a matriz (Arc C).
    from shopman.shop.services.catalog_sync import sync_status_map

    sync_map = sync_status_map(skus)

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
            # Feed (menuboard/plataforma): célula = pertence ao feed (via coleções) e
            # pausa local; sem preço/publicação. A pausa global do produto gateia por cima.
            sync_status, sync_error, synced_at = _cell_sync(sync_map, product.sku, surface.sync_key or surface.ref)
            if surface.ref in showcase_index:
                sc = showcase_index[surface.ref]
                in_showcase = product.sku in sc["members"]
                paused_here = product.sku in sc["paused"]
                cells.append(
                    SurfaceCellProjection(
                        surface_ref=surface.ref,
                        in_listing=in_showcase,
                        is_published=in_showcase,
                        is_sellable=in_showcase and not paused_here,
                        available=(
                            in_showcase
                            and not paused_here
                            and product.is_published
                            and product.is_sellable
                        ),
                        price_q=None,
                        price_display="",
                        sync_status=sync_status,
                        sync_error=sync_error,
                        synced_at=synced_at,
                    )
                )
                continue

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
                        sync_status=sync_status,
                        sync_error=sync_error,
                        synced_at=synced_at,
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
                    sync_status=sync_status,
                    sync_error=sync_error,
                    synced_at=synced_at,
                )
            )

        stock = _stock_view(
            stock_by_sku.get(product.sku), low_stock_threshold, planned_by_sku.get(product.sku, 0)
        )
        social_view, pim_complete = _social_view(product)
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
                social=social_view,
                pim_complete=pim_complete,
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
