"""
Projeção dos Feeds (Showcase) para o Gestor — o lado DISPLAY do cardápio.

Um Feed exibe um recorte de coleções para fora (📺 menuboard / 🛰 Google/Meta) sem
transacionar. Esta projeção lista os feeds + a saída (URL para abrir/prever) +
as coleções disponíveis (para o operador escolher quais cada um mostra). A ordem de
exibição das coleções é global (``Collection.sort_order``), reordenável no catálogo.

Read-only. Frozen dataclasses convertidos por ``backstage.api.projections``.
"""

from __future__ import annotations

from dataclasses import dataclass

_KIND_META = {
    "menuboard": {"label": "Menuboard (TV)", "icon": "tv", "capability": "display"},
    "google": {"label": "Feed Google", "icon": "rss", "capability": "feed"},
    "meta": {"label": "Feed Meta", "icon": "rss", "capability": "feed"},
}


def _output_path(showcase) -> str:
    """Caminho público da saída do feed (abrir/prever)."""
    if showcase.kind == "menuboard":
        return f"/menuboard/{showcase.ref}/"
    if showcase.kind == "meta":
        return f"/feed/{showcase.ref}.xml?platform=meta"
    if showcase.kind == "google":
        return f"/feed/{showcase.ref}.xml"
    return ""


@dataclass(frozen=True)
class ShowcaseCollectionRef:
    ref: str
    name: str
    exists: bool  # a coleção ainda existe?


@dataclass(frozen=True)
class ShowcaseProjection:
    ref: str
    name: str
    kind: str
    kind_label: str
    kind_icon: str
    capability: str  # display | feed
    is_active: bool
    output_path: str
    collections: tuple[ShowcaseCollectionRef, ...]  # coleções que ele exibe (em ordem global)


@dataclass(frozen=True)
class CollectionOptionProjection:
    ref: str
    name: str
    product_count: int


@dataclass(frozen=True)
class ShowcaseBoardProjection:
    showcases: tuple[ShowcaseProjection, ...]
    all_collections: tuple[CollectionOptionProjection, ...]  # opções p/ o picker (ordem global)


def build_showcase_board() -> ShowcaseBoardProjection:
    from shopman.offerman.models import Collection

    from shopman.shop.models import Showcase

    collections = list(Collection.objects.filter(is_active=True).order_by("sort_order", "name"))
    coll_by_ref = {c.ref: c for c in collections}
    order_index = {c.ref: i for i, c in enumerate(collections)}

    showcases: list[ShowcaseProjection] = []
    for sc in Showcase.objects.all().order_by("name"):
        meta = _KIND_META.get(sc.kind, {"label": sc.kind, "icon": "monitor", "capability": "display"})
        # resolve + ordena as coleções do feed pela ordem global (sort_order)
        refs = sc.collection_refs()
        resolved = [
            ShowcaseCollectionRef(
                ref=r,
                name=coll_by_ref[r].name if r in coll_by_ref else r,
                exists=r in coll_by_ref,
            )
            for r in refs
        ]
        resolved.sort(key=lambda c: order_index.get(c.ref, 10_000))
        showcases.append(
            ShowcaseProjection(
                ref=sc.ref,
                name=sc.name or sc.ref,
                kind=sc.kind,
                kind_label=meta["label"],
                kind_icon=meta["icon"],
                capability=meta["capability"],
                is_active=sc.is_active,
                output_path=_output_path(sc),
                collections=tuple(resolved),
            )
        )

    options = tuple(
        CollectionOptionProjection(ref=c.ref, name=c.name, product_count=c.product_queryset().count())
        for c in collections
    )
    return ShowcaseBoardProjection(showcases=tuple(showcases), all_collections=options)
