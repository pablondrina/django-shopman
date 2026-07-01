"""
Catalog mutation facade — pausa/publica/preço por superfície + bulk.

Estratégia de projeção (ponte da Frente 1):
- **Célula única** → ``ListingItem.save()``: emite ``availability_changed`` /
  ``price_changed``; o auto-trigger enfileira a projeção só para superfícies com
  backend na registry canônica (as demais são no-op). Preserva history.
- **Bulk** (scoped a coleção/superfície/seleção) → ``queryset.update()`` (rápido,
  consistente com as bulk actions do admin) **+ reconciliação única** via
  ``CatalogService.project_listing`` quando a superfície é alvo de projeção
  (retract-aware, um reconcile em vez de N directives).

Escreve direto nos models do offerman (como as projections do backstage já leem).
Superfície = Channel; célula = ListingItem da listing de mesmo ref.
"""

from __future__ import annotations

from shopman.backstage.services.exceptions import CatalogError


def _reconcile_if_projected(surface_ref: str) -> None:
    """Reconcilia a superfície (retract-aware) só se ela tem backend de projeção."""
    from shopman.offerman.conf import get_projection_backend

    if get_projection_backend(surface_ref) is None:
        return
    from shopman.offerman.exceptions import CatalogError as OffermanCatalogError
    from shopman.offerman.service import CatalogService

    try:
        CatalogService.project_listing(surface_ref)
    except OffermanCatalogError as exc:
        # Reconciliação é best-effort: a mutação no DB já valeu; a projeção externa
        # é retentada pelo auto-trigger/comando. Não derruba a operação do operador.
        raise CatalogError(f"Mudança aplicada, mas a sincronização falhou: {exc}") from exc


def _notify_surface(surface_ref: str) -> None:
    """Empurra o evento SSE da superfície (bulk não dispara post_save → menuboard)."""
    from shopman.shop.handlers._sse_emitters import emit_surface_changed

    emit_surface_changed(surface_ref)


# Sentinela "todos os canais" para as ações em lote (barra flutuante).
ALL_SURFACES = "*"


def _all_channel_refs() -> list[str]:
    from shopman.shop.models import Channel

    return list(Channel.objects.filter(is_active=True).order_by("display_order", "id").values_list("ref", flat=True))


def set_cell(
    sku: str,
    surface_ref: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    price_q: int | None = None,
    actor: str = "",
):
    """Edita uma célula (produto × superfície). save() dispara o auto-trigger."""
    from shopman.offerman.models import ListingItem

    item = (
        ListingItem.objects.filter(listing__ref=surface_ref, product__sku=sku)
        .select_related("product", "listing")
        .order_by("min_qty")
        .first()
    )
    if item is None:
        raise CatalogError(f"Produto '{sku}' não está na superfície '{surface_ref}'.")

    if price_q is not None:
        if price_q < 0:
            raise CatalogError("Preço não pode ser negativo.")
        item.price_q = price_q
    if is_published is not None:
        item.is_published = is_published
    if is_sellable is not None:
        item.is_sellable = is_sellable

    item.save()
    return item


def set_product(
    sku: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    actor: str = "",
):
    """Pausa/publica o produto em TODOS os canais de uma vez ("globalzinho").

    Escreve no switch produto-level (``Product.is_sellable`` / ``is_published``),
    que gateia toda superfície. ``save()`` emite ``product_updated`` → o auto-trigger
    re-projeta o produto em cada listing alvo (retract-aware). Um único ponto de
    verdade; não itera célula por célula.
    """
    from shopman.offerman.models import Product

    product = Product.objects.filter(sku=sku).first()
    if product is None:
        raise CatalogError(f"Produto '{sku}' não encontrado.")

    if is_published is None and is_sellable is None:
        raise CatalogError("Nada a atualizar (informe is_published e/ou is_sellable).")
    if is_published is not None:
        product.is_published = is_published
    if is_sellable is not None:
        product.is_sellable = is_sellable

    product.save()
    return product


def bulk_set(
    skus: list[str],
    surface_ref: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    actor: str = "",
) -> int:
    """Aplica pausa/publicação em lote numa superfície e reconcilia uma vez.

    Retorna o número de células afetadas.
    """
    from shopman.offerman.models import ListingItem

    if not skus:
        return 0
    if surface_ref == ALL_SURFACES:
        return sum(
            bulk_set(skus, ref, is_published=is_published, is_sellable=is_sellable, actor=actor)
            for ref in _all_channel_refs()
        )
    updates: dict[str, bool] = {}
    if is_published is not None:
        updates["is_published"] = is_published
    if is_sellable is not None:
        updates["is_sellable"] = is_sellable
    if not updates:
        raise CatalogError("Nada a atualizar (informe is_published e/ou is_sellable).")

    count = (
        ListingItem.objects.filter(listing__ref=surface_ref, product__sku__in=skus).update(**updates)
    )
    if count:
        _reconcile_if_projected(surface_ref)
        _notify_surface(surface_ref)
    return count


def bulk_set_collection(
    collection_ref: str,
    surface_ref: str,
    *,
    is_published: bool | None = None,
    is_sellable: bool | None = None,
    actor: str = "",
) -> int:
    """Bulk scoped a uma COLEÇÃO (manual ou smart) numa superfície.

    Resolve os produtos da coleção (regra ou explícitos) e aplica em lote.
    """
    from shopman.offerman.models import Collection

    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise CatalogError(f"Coleção '{collection_ref}' não encontrada.")
    skus = list(coll.product_queryset().values_list("sku", flat=True))
    return bulk_set(
        skus, surface_ref, is_published=is_published, is_sellable=is_sellable, actor=actor
    )


_PRICE_OPS = ("set", "pct", "delta")


def _apply_price_op(old_q: int, op: str, value: int) -> int:
    """Aplica a operação de preço a um valor em centavos (nunca negativo)."""
    from decimal import ROUND_HALF_UP, Decimal

    if op == "set":
        new_q = int(value)
    elif op == "pct":
        factor = Decimal(1) + (Decimal(value) / Decimal(100))
        new_q = int((Decimal(old_q) * factor).to_integral_value(rounding=ROUND_HALF_UP))
    else:  # delta
        new_q = old_q + int(value)
    return max(new_q, 0)


def bulk_price(
    skus: list[str],
    surface_ref: str,
    *,
    op: str,
    value: int,
    actor: str = "",
) -> int:
    """Reprecifica em lote o tier base de cada produto numa superfície.

    ``op``: ``set`` (preço absoluto, centavos) · ``pct`` (ajuste percentual, pontos
    +/-) · ``delta`` (ajuste absoluto, centavos +/-). Calcula em Python (arredonda),
    grava num único ``bulk_update`` e reconcilia uma vez (padrão do bulk).

    Reprecificação é PERMANENTE (muda o cardápio). Para promoção temporária, use o
    motor de regras (Happy Hour/D-1), não isto.
    """
    from shopman.offerman.models import ListingItem

    if op not in _PRICE_OPS:
        raise CatalogError(f"Operação de preço inválida: {op!r}.")
    if op == "set" and value < 0:
        raise CatalogError("Preço não pode ser negativo.")
    if not skus:
        return 0
    if surface_ref == ALL_SURFACES:
        return sum(bulk_price(skus, ref, op=op, value=value, actor=actor) for ref in _all_channel_refs())

    # tier base (menor min_qty) por SKU — 1 célula por produto, como a matriz mostra.
    items = (
        ListingItem.objects.filter(listing__ref=surface_ref, product__sku__in=skus)
        .select_related("product")
        .order_by("product__sku", "min_qty")
    )
    seen: set[str] = set()
    changed: list = []
    for item in items:
        sku = item.product.sku
        if sku in seen:
            continue
        seen.add(sku)
        new_q = _apply_price_op(item.price_q, op, value)
        if new_q != item.price_q:
            item.price_q = new_q
            changed.append(item)

    if changed:
        ListingItem.objects.bulk_update(changed, ["price_q"])
        _reconcile_if_projected(surface_ref)
        _notify_surface(surface_ref)
    return len(changed)


def bulk_price_collection(
    collection_ref: str,
    surface_ref: str,
    *,
    op: str,
    value: int,
    actor: str = "",
) -> int:
    """Reprecificação em lote scoped a uma COLEÇÃO (manual ou smart)."""
    from shopman.offerman.models import Collection

    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise CatalogError(f"Coleção '{collection_ref}' não encontrada.")
    skus = list(coll.product_queryset().values_list("sku", flat=True))
    return bulk_price(skus, surface_ref, op=op, value=value, actor=actor)


# ── reordenação (curadoria da vitrine) ─────────────────────────────────────────
# A ordem do cardápio vive em Collection.sort_order (seções) e CollectionItem.sort_order
# (produtos dentro da coleção). Storefront, menuboard e feeds usam essa ordem.


def reorder_collections(ordered_refs: list[str], *, actor: str = "") -> int:
    """Grava a ordem das coleções (Collection.sort_order) na sequência recebida."""
    from shopman.offerman.models import Collection

    if not ordered_refs:
        return 0
    colls = {c.ref: c for c in Collection.objects.filter(ref__in=ordered_refs)}
    changed = []
    for index, ref in enumerate(ordered_refs):
        coll = colls.get(ref)
        if coll is not None and coll.sort_order != index:
            coll.sort_order = index
            changed.append(coll)
    if changed:
        Collection.objects.bulk_update(changed, ["sort_order"])
    return len(changed)


def reorder_collection_items(collection_ref: str, ordered_skus: list[str], *, actor: str = "") -> int:
    """Grava a ordem dos produtos dentro de uma coleção MANUAL (CollectionItem.sort_order).

    Coleção por regra (smart) não tem ordem manual — a pertinência é por condição.
    """
    from shopman.offerman.models import Collection, CollectionItem

    coll = Collection.objects.filter(ref=collection_ref).first()
    if coll is None:
        raise CatalogError(f"Coleção '{collection_ref}' não encontrada.")
    if coll.is_smart:
        raise CatalogError("Coleção por regra não tem ordem manual.")
    if not ordered_skus:
        return 0

    items = {
        ci.product.sku: ci
        for ci in CollectionItem.objects.filter(collection=coll).select_related("product")
    }
    changed = []
    for index, sku in enumerate(ordered_skus):
        ci = items.get(sku)
        if ci is not None and ci.sort_order != index:
            ci.sort_order = index
            changed.append(ci)
    if changed:
        CollectionItem.objects.bulk_update(changed, ["sort_order"])
    return len(changed)


