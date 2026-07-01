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
