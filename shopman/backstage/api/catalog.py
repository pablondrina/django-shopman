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
from shopman.backstage.services.exceptions import (
    AiAssistError,
    AiAssistNotConfigured,
    CatalogError,
)


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


class CatalogProductView(_CatalogBase):
    """Pausa/publica o produto em TODOS os canais de uma vez ("globalzinho")."""

    def post(self, request):
        sku = (request.data.get("sku") or "").strip()
        if not sku:
            return Response({"detail": "sku é obrigatório."}, status=400)

        is_published = request.data.get("is_published")
        is_sellable = request.data.get("is_sellable")
        if is_published is None and is_sellable is None:
            return Response({"detail": "Informe is_published e/ou is_sellable."}, status=400)

        try:
            product = catalog_service.set_product(
                sku,
                is_published=is_published,
                is_sellable=is_sellable,
                actor=_actor(request),
            )
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            {
                "ok": True,
                "sku": sku,
                "is_published": product.is_published,
                "is_sellable": product.is_sellable,
            }
        )


class CatalogProductDetailView(_CatalogBase):
    """Lê/edita os campos escalares de UM produto (painel de produto do Gestor).

    GET devolve todos os campos editáveis + contexto somente-leitura (SKU, coleção
    primária). PATCH faz merge parcial: chave ausente no corpo mantém o valor atual.
    A escrita passa por ``full_clean`` + ``save`` no facade (preserva a re-projeção).
    """

    def get(self, request, sku: str):
        try:
            return Response({"product": catalog_service.get_product_detail(sku)})
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=404)

    def patch(self, request, sku: str):
        try:
            product = catalog_service.update_product_detail(
                sku, request.data, actor=_actor(request)
            )
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"ok": True, "product": product})


class CatalogAiAssistView(_CatalogBase):
    """Sugere o conteúdo de UM campo de texto de um produto (assist de IA).

    Por campo, nunca em lote: o operador pede a sugestão de um campo e aceita ou
    descarta ela sozinha na superfície. Não grava nada — quem persiste é o PATCH
    do produto (ou o POST social), depois do "Aceitar".

    503 quando o deployment não tem ``AI_ASSIST_API_KEY``: a superfície mostra um
    aviso, não um erro. O assist é conveniência, não caminho crítico.
    """

    def post(self, request):
        sku = (request.data.get("sku") or "").strip()
        field = (request.data.get("field") or "").strip()
        if not sku or not field:
            return Response({"detail": "sku e field são obrigatórios."}, status=400)

        try:
            suggestion = catalog_service.ai_assist_field(
                sku, field, current_value=str(request.data.get("current_value") or "")
            )
        except AiAssistNotConfigured as exc:
            return Response({"detail": str(exc)}, status=503)
        except AiAssistError as exc:
            return Response({"detail": str(exc)}, status=502)
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"suggestion": suggestion})


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


class CatalogBulkPriceView(_CatalogBase):
    """Reprecificação em lote scoped a superfície + (coleção | seleção de skus)."""

    def post(self, request):
        surface_ref = (request.data.get("surface_ref") or "").strip()
        op = (request.data.get("op") or "").strip()
        value = _as_int(request.data.get("value"))
        if not surface_ref:
            return Response({"detail": "surface_ref é obrigatório."}, status=400)
        if op not in ("set", "pct", "delta"):
            return Response({"detail": "op deve ser set, pct ou delta."}, status=400)
        if value is None:
            return Response({"detail": "value é obrigatório."}, status=400)

        collection_ref = (request.data.get("collection_ref") or "").strip()
        skus = request.data.get("skus") or []

        try:
            if collection_ref:
                count = catalog_service.bulk_price_collection(
                    collection_ref, surface_ref, op=op, value=value, actor=_actor(request)
                )
            elif isinstance(skus, list) and skus:
                count = catalog_service.bulk_price(
                    [str(s).strip() for s in skus],
                    surface_ref,
                    op=op,
                    value=value,
                    actor=_actor(request),
                )
            else:
                return Response(
                    {"detail": "Informe collection_ref ou uma lista skus."}, status=400
                )
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response({"ok": True, "surface_ref": surface_ref, "count": count})


class CatalogReorderCollectionsView(_CatalogBase):
    """Ordena as coleções (seções da vitrine) na sequência recebida."""

    def post(self, request):
        ordered = request.data.get("ordered_refs")
        if not isinstance(ordered, list) or not ordered:
            return Response({"detail": "ordered_refs (lista) é obrigatório."}, status=400)
        count = catalog_service.reorder_collections(
            [str(r).strip() for r in ordered], actor=_actor(request)
        )
        return Response({"ok": True, "count": count})


class CatalogReorderItemsView(_CatalogBase):
    """Ordena os produtos dentro de uma coleção manual."""

    def post(self, request):
        collection_ref = (request.data.get("collection_ref") or "").strip()
        ordered = request.data.get("ordered_skus")
        if not collection_ref:
            return Response({"detail": "collection_ref é obrigatório."}, status=400)
        if not isinstance(ordered, list) or not ordered:
            return Response({"detail": "ordered_skus (lista) é obrigatório."}, status=400)
        try:
            count = catalog_service.reorder_collection_items(
                collection_ref, [str(s).strip() for s in ordered], actor=_actor(request)
            )
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"ok": True, "count": count})


class CatalogSyncStatusView(_CatalogBase):
    """Estado de sync por produto × plataforma (para o selo de cada célula)."""

    def get(self, request):
        from shopman.shop.services.catalog_sync import sync_status_map

        platform = (request.query_params.get("platform") or "").strip() or None
        skus_param = (request.query_params.get("sku") or "").strip()
        skus = [s for s in (part.strip() for part in skus_param.split(",")) if s] or None
        return Response({"sync_status": sync_status_map(skus, platform=platform)})


class CatalogSocialView(_CatalogBase):
    """Lê/salva os atributos PIM sociais (Product.metadata['social']) de um SKU.

    O painel PIM da matriz edita marca/GTIN/categoria/hashtags e salva aqui. A
    escrita valida via ``ProductSocialAttributes.errors()`` e persiste com
    ``set_social_attributes`` (só chaves não-default) — sem migração (padrão
    fiscal/nutrition). Salvar re-projeta via o gatilho de ``Product.save``.
    """

    def get(self, request):
        from shopman.offerman import get_social_attributes
        from shopman.offerman.models import Product

        sku = (request.query_params.get("sku") or "").strip()
        if not sku:
            return Response({"detail": "sku é obrigatório."}, status=400)
        product = Product.objects.filter(sku=sku).first()
        if product is None:
            return Response({"detail": "Produto não encontrado."}, status=404)
        return Response({"sku": sku, "social": _social_payload(get_social_attributes(product))})

    def post(self, request):
        from shopman.offerman import (
            ProductSocialAttributes,
            get_social_attributes,
            set_social_attributes,
        )
        from shopman.offerman.models import Product

        sku = (request.data.get("sku") or "").strip()
        if not sku:
            return Response({"detail": "sku é obrigatório."}, status=400)
        product = Product.objects.filter(sku=sku).first()
        if product is None:
            return Response({"detail": "Produto não encontrado."}, status=404)

        current = get_social_attributes(product)
        data = request.data
        # Merge parcial: campo ausente no corpo mantém o valor atual.
        attrs = ProductSocialAttributes(
            brand=_field(data, "brand", current.brand),
            gtin=_field(data, "gtin", current.gtin),
            mpn=_field(data, "mpn", current.mpn),
            condition=_field(data, "condition", current.condition),
            google_product_category=_field(
                data, "google_product_category", current.google_product_category
            ),
            tiktok_category_id=_field(data, "tiktok_category_id", current.tiktok_category_id),
            hashtags=data["hashtags"] if "hashtags" in data else list(current.hashtags),
            social_caption=_field(data, "social_caption", current.social_caption),
        )
        problems = attrs.errors()
        if problems:
            return Response({"detail": problems[0], "errors": problems}, status=400)

        product.metadata = set_social_attributes(product.metadata, attrs)
        product.save(update_fields=["metadata"])
        return Response({"ok": True, "sku": sku, "social": _social_payload(attrs)})


class CatalogResyncView(_CatalogBase):
    """Re-enfileira a projeção de um SKU (uma plataforma ou todas as configuradas)."""

    def post(self, request):
        sku = (request.data.get("sku") or "").strip()
        platform = (request.data.get("platform") or "").strip()
        if not sku:
            return Response({"detail": "sku é obrigatório."}, status=400)

        from shopman.offerman.conf import get_projection_backend_channels

        from shopman.shop.handlers.catalog_projection import enqueue_project

        targets = [platform] if platform else list(get_projection_backend_channels())
        for listing_ref in targets:
            enqueue_project(sku, listing_ref, trigger="manual_resync")
        return Response({"ok": True, "sku": sku, "platforms": targets})


def _field(data, key: str, current: str) -> str:
    """Valor textual do corpo (aparado) ou o atual quando a chave está ausente."""
    if key not in data:
        return current
    return str(data.get(key) or "").strip()


def _social_payload(attrs) -> dict:
    return {
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


def _as_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
