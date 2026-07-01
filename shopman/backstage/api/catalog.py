"""
Backstage Catalog API — matriz produto × superfície (read) + mutações (write).

Contrato consumido pelo Gestor (Nuxt). Read = projection da matriz; write =
pausa/publica/preço por célula e bulk scoped a superfície/coleção/seleção.
Gate: ``shop.manage_catalog``. Mutações delegam ao facade
``backstage.services.catalog`` (que dispara o auto-trigger / reconcilia).
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data
from shopman.backstage.services import catalog as catalog_service
from shopman.backstage.services.exceptions import CatalogError


def _actor(request) -> str:
    operator = getattr(request, "active_operator_user", None)
    if operator is not None:
        return operator.get_username()
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "operator"


class _CatalogBase(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_catalog"


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Catalog matrix (produto × superfície)",
        responses={200: OpenApiResponse(description="Matriz de catálogo por superfície.")},
    ),
)
class CatalogMatrixView(_CatalogBase):
    def get(self, request):
        from shopman.backstage.projections.catalog import build_catalog_matrix

        collection_ref = (request.query_params.get("collection") or "").strip()
        matrix = build_catalog_matrix(collection_ref)
        return Response({"matrix": projection_data(matrix)})


class CatalogCellView(_CatalogBase):
    """Edita uma célula: pausa/publica/preço de um produto numa superfície."""

    def post(self, request):
        sku = (request.data.get("sku") or "").strip()
        surface_ref = (request.data.get("surface_ref") or "").strip()
        if not sku or not surface_ref:
            return Response({"detail": "sku e surface_ref são obrigatórios."}, status=400)

        try:
            item = catalog_service.set_cell(
                sku,
                surface_ref,
                is_published=request.data.get("is_published"),
                is_sellable=request.data.get("is_sellable"),
                price_q=_as_int(request.data.get("price_q")),
                actor=_actor(request),
            )
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            {
                "ok": True,
                "sku": sku,
                "surface_ref": surface_ref,
                "is_published": item.is_published,
                "is_sellable": item.is_sellable,
                "price_q": item.price_q,
            }
        )


class CatalogBulkView(_CatalogBase):
    """Bulk pausa/publica scoped a superfície + (coleção | seleção de skus)."""

    def post(self, request):
        surface_ref = (request.data.get("surface_ref") or "").strip()
        if not surface_ref:
            return Response({"detail": "surface_ref é obrigatório."}, status=400)

        is_published = request.data.get("is_published")
        is_sellable = request.data.get("is_sellable")
        if is_published is None and is_sellable is None:
            return Response(
                {"detail": "Informe is_published e/ou is_sellable."}, status=400
            )

        collection_ref = (request.data.get("collection_ref") or "").strip()
        skus = request.data.get("skus") or []

        try:
            if collection_ref:
                count = catalog_service.bulk_set_collection(
                    collection_ref,
                    surface_ref,
                    is_published=is_published,
                    is_sellable=is_sellable,
                    actor=_actor(request),
                )
            elif isinstance(skus, list) and skus:
                count = catalog_service.bulk_set(
                    [str(s).strip() for s in skus],
                    surface_ref,
                    is_published=is_published,
                    is_sellable=is_sellable,
                    actor=_actor(request),
                )
            else:
                return Response(
                    {"detail": "Informe collection_ref ou uma lista skus."}, status=400
                )
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"ok": True, "surface_ref": surface_ref, "count": count})


class CatalogMaterializeView(_CatalogBase):
    """Sincroniza os ListingItems de uma superfície a partir da coleção-fonte."""

    def post(self, request):
        surface_ref = (request.data.get("surface_ref") or "").strip()
        if not surface_ref:
            return Response({"detail": "surface_ref é obrigatório."}, status=400)
        try:
            result = catalog_service.materialize_surface(surface_ref, actor=_actor(request))
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"ok": True, "surface_ref": surface_ref, **result})


def _as_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
