"""FOMO badges API — urgência real de um SKU, pública e cacheada.

Fetch canônico do push SSE (ADR-016): o evento no canal ``fomo-<sku>`` só diz
"mudou"; o cliente volta aqui para saber o quê. Por isso o TTL é curto e o
emissor invalida a chave no commit.
"""

from __future__ import annotations

from dataclasses import asdict

from django.core.cache import cache
from django.http import Http404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services.fomo import cache_key
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.services import catalog as catalog_service
from shopman.storefront.services import fomo as fomo_service

CACHE_TTL_SECONDS = 10


@extend_schema_view(
    get=extend_schema(
        tags=["availability"],
        summary="FOMO badges for a product",
        parameters=[
            OpenApiParameter("channel", str, description="Optional channel scope."),
        ],
    ),
)
class FomoBadgesView(APIView):
    """
    GET /api/v1/fomo/<sku>/?channel=<channel_ref>

    Response:
        {
            "sku": str,
            "badges": [
                {"type": str, "label": str, "priority": int,
                 "expires_at": str | null, "meta": {...}}
            ]
        }

    Lista vazia é resposta normal: a maioria dos produtos não tem urgência.
    """

    authentication_classes = []
    permission_classes = []

    def get(self, request, sku):
        if not catalog_service.product_exists(sku):
            raise Http404

        channel_ref = request.GET.get("channel")
        key = cache_key(sku, channel_ref)

        cached = cache.get(key)
        if cached is not None:
            return Response(cached)

        badges = fomo_service.badges_for_sku(
            sku, channel_ref=channel_ref or STOREFRONT_CHANNEL_REF
        )
        data = {"sku": sku, "badges": [asdict(badge) for badge in badges]}

        cache.set(key, data, CACHE_TTL_SECONDS)
        return Response(data)
