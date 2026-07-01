"""
Backstage Showcase API — Expositores (menuboard/feeds) no Gestor.

Read = board dos expositores + coleções disponíveis; write = ligar/pausar e escolher
as coleções que cada expositor exibe. Gate: ``shop.manage_catalog``.
"""

from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.api.permissions import HasBackstagePermission
from shopman.backstage.api.projections import projection_data
from shopman.backstage.services import showcase as showcase_service
from shopman.backstage.services.exceptions import CatalogError


class _ShowcaseBase(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "shop.manage_catalog"


class ShowcaseBoardView(_ShowcaseBase):
    def get(self, request):
        from shopman.backstage.projections.showcase import build_showcase_board

        return Response({"board": projection_data(build_showcase_board())})


class ShowcaseActiveView(_ShowcaseBase):
    def post(self, request):
        ref = (request.data.get("ref") or "").strip()
        is_active = request.data.get("is_active")
        if not ref or not isinstance(is_active, bool):
            return Response({"detail": "ref e is_active (bool) são obrigatórios."}, status=400)
        try:
            showcase_service.set_active(ref, is_active)
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"ok": True, "ref": ref, "is_active": is_active})


class ShowcaseCollectionsView(_ShowcaseBase):
    def post(self, request):
        ref = (request.data.get("ref") or "").strip()
        collections = request.data.get("collections")
        if not ref or not isinstance(collections, list):
            return Response({"detail": "ref e collections (lista) são obrigatórios."}, status=400)
        try:
            showcase_service.set_collections(ref, collections)
        except CatalogError as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"ok": True, "ref": ref})
