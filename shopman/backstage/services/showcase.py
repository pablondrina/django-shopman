"""
Mutações dos Expositores (Showcase) para o Gestor — ligar/pausar + escolher coleções.

Escreve direto no model ``shop.Showcase`` (como as projections do backstage já leem) e
sinaliza a superfície de display (menuboard) para atualizar em tempo real.
"""

from __future__ import annotations

from shopman.backstage.services.exceptions import CatalogError


def _notify(ref: str) -> None:
    """Empurra o evento SSE p/ a superfície de display (menuboard atualiza na hora)."""
    from shopman.shop.handlers._sse_emitters import emit_surface_changed

    emit_surface_changed(ref)


def set_active(ref: str, is_active: bool) -> None:
    from shopman.shop.models import Showcase

    sc = Showcase.objects.filter(ref=ref).first()
    if sc is None:
        raise CatalogError(f"Expositor '{ref}' não encontrado.")
    if sc.is_active != is_active:
        sc.is_active = is_active
        sc.save(update_fields=["is_active", "updated_at"])
        _notify(ref)


def set_collections(ref: str, collection_refs: list[str]) -> None:
    """Define quais coleções o expositor exibe (a ORDEM é global, via Collection.sort_order)."""
    from shopman.offerman.models import Collection

    from shopman.shop.models import Showcase

    sc = Showcase.objects.filter(ref=ref).first()
    if sc is None:
        raise CatalogError(f"Expositor '{ref}' não encontrado.")

    cleaned = [str(r).strip() for r in collection_refs if str(r).strip()]
    valid = set(Collection.objects.filter(ref__in=cleaned).values_list("ref", flat=True))
    unknown = [r for r in cleaned if r not in valid]
    if unknown:
        raise CatalogError(f"Coleção(ões) inexistente(s): {', '.join(unknown)}.")

    # dedup preservando a ordem de chegada (a exibição reordena por sort_order de qq jeito)
    seen: set[str] = set()
    ordered = [r for r in cleaned if not (r in seen or seen.add(r))]
    if ordered != sc.collection_refs():
        sc.collections = ordered
        sc.save(update_fields=["collections", "updated_at"])
        _notify(ref)


def set_item_paused(ref: str, sku: str, *, paused: bool) -> bool:
    """Pausa/reativa UM item neste expositor (equivalente a pausar num canal).

    Grava em ``Showcase.options["paused_skus"]`` (JSONField, sem migração). Retorna o
    estado final ``paused``. A pausa global do produto continua gateando por cima.
    """
    from shopman.shop.models import Showcase

    sku = str(sku).strip()
    if not sku:
        raise CatalogError("sku é obrigatório.")
    sc = Showcase.objects.filter(ref=ref).first()
    if sc is None:
        raise CatalogError(f"Expositor '{ref}' não encontrado.")

    current = sc.paused_skus()
    if paused and sku not in current:
        current.add(sku)
    elif not paused and sku in current:
        current.discard(sku)
    else:
        return paused  # sem mudança

    options = dict(sc.options or {})
    options["paused_skus"] = sorted(current)
    sc.options = options
    sc.save(update_fields=["options", "updated_at"])
    _notify(ref)
    return paused


def set_items_paused(ref: str, skus: list[str], *, paused: bool) -> int:
    """Pausa/reativa em lote vários itens neste expositor. Retorna quantos mudaram."""
    from shopman.shop.models import Showcase

    cleaned = [str(s).strip() for s in skus if str(s).strip()]
    if not cleaned:
        return 0
    sc = Showcase.objects.filter(ref=ref).first()
    if sc is None:
        raise CatalogError(f"Expositor '{ref}' não encontrado.")

    current = sc.paused_skus()
    before = set(current)
    if paused:
        current.update(cleaned)
    else:
        current.difference_update(cleaned)
    if current == before:
        return 0

    options = dict(sc.options or {})
    options["paused_skus"] = sorted(current)
    sc.options = options
    sc.save(update_fields=["options", "updated_at"])
    _notify(ref)
    return len(current ^ before)
