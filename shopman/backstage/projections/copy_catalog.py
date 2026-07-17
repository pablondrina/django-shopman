"""CopyCatalogProjection — read model do catálogo de copy omotenashi.

O changelist de OmotenashiCopy lista OVERRIDES (linhas no banco); o problema de
descoberta é o inverso: o operador viu um texto NA TELA e precisa achar a CHAVE.
Este read model inverte o índice: TODAS as chaves registradas (código), agrupadas
por superfície → tela (mapa chave↔tela derivado do código, ver
``shopman.shop.omotenashi.usage``), com o default, o estado de override e os
links de edição.

Consumido pela página Admin canônica ``admin_console/copy_catalog``.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.urls import reverse

from shopman.shop.models import OmotenashiCopy
from shopman.shop.omotenashi.copy import OMOTENASHI_DEFAULTS, default_for
from shopman.shop.omotenashi.usage import UNMAPPED_SURFACE, load_usage_map


@dataclass(frozen=True)
class CopyCatalogRow:
    key: str
    default_title: str
    default_message: str
    variant_count: int  # combinações momento×público definidas no código
    override_count: int  # overrides ATIVOS no banco
    other_screens: str  # "Sacola · Pagamento" quando a chave aparece em mais telas
    add_url: str
    list_url: str


@dataclass(frozen=True)
class CopyCatalogGroup:
    surface: str
    screen: str
    rows: tuple[CopyCatalogRow, ...]


@dataclass(frozen=True)
class CopyCatalogProjection:
    groups: tuple[CopyCatalogGroup, ...]
    surfaces: tuple[str, ...]
    total_keys: int
    mapped_keys: int
    active_overrides: int
    q: str
    surface: str


def _variant_count(key: str) -> int:
    by_moment = OMOTENASHI_DEFAULTS.get(key, {})
    return sum(len(by_audience) for by_audience in by_moment.values())


def build_copy_catalog(q: str = "", surface: str = "") -> CopyCatalogProjection:
    usage = load_usage_map()
    overrides: dict[str, int] = {}
    for row in OmotenashiCopy.objects.filter(active=True).values_list("key", flat=True):
        overrides[row] = overrides.get(row, 0) + 1

    add_base = reverse("admin:shop_omotenashicopy_add")
    list_base = reverse("admin:shop_omotenashicopy_changelist")

    needle = q.strip().lower()

    # chave → conjunto de (superfície, tela); sem uso ⇒ balde honesto de revisão.
    grouped: dict[tuple[str, str], list[CopyCatalogRow]] = {}
    mapped_keys = 0
    for key in sorted(usage):
        refs = usage[key]
        screens = sorted({(ref.surface, ref.screen) for ref in refs})
        if screens:
            mapped_keys += 1
        else:
            screens = [(UNMAPPED_SURFACE, "Sem uso mapeado")]

        entry = default_for(key)
        if needle and not (
            needle in key.lower()
            or needle in entry.title.lower()
            or needle in entry.message.lower()
        ):
            continue

        for surface_label, screen_label in screens:
            if surface and surface_label != surface:
                continue
            others = " · ".join(
                s for _, s in screens if (surface_label, s) not in [(surface_label, screen_label)]
            )
            grouped.setdefault((surface_label, screen_label), []).append(
                CopyCatalogRow(
                    key=key,
                    default_title=entry.title,
                    default_message=entry.message,
                    variant_count=_variant_count(key),
                    override_count=overrides.get(key, 0),
                    other_screens=others,
                    add_url=f"{add_base}?key={key}",
                    list_url=f"{list_base}?q={key}",
                )
            )

    all_surfaces = sorted(
        {ref.surface for refs in usage.values() for ref in refs} | {UNMAPPED_SURFACE}
    )

    groups = tuple(
        CopyCatalogGroup(surface=s, screen=t, rows=tuple(rows))
        for (s, t), rows in sorted(grouped.items())
    )
    return CopyCatalogProjection(
        groups=groups,
        surfaces=tuple(all_surfaces),
        total_keys=len(usage),
        mapped_keys=mapped_keys,
        active_overrides=sum(overrides.values()),
        q=q,
        surface=surface,
    )
