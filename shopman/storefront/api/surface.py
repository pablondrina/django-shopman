"""API-first storefront surface endpoints.

These endpoints expose the same projection layer used by the Django templates,
so an alternate client can swap the outer surface without duplicating business
rules.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.projections import (
    build_cart,
    build_catalog,
    build_product_detail,
)
from shopman.storefront.services import catalog as catalog_service
from shopman.storefront.services.cart_mutations import (
    CartCommandNotFound,
    CartCommandUnavailable,
    set_qty_by_sku,
)

from .projections import projection_data
from .serializers import DetailSerializer, SetSkuQtySerializer


def _cart_payload(request) -> dict:
    cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
    return projection_data(cart)


def _stock_error_payload(exc) -> dict:
    return {
        "detail": "Insufficient stock.",
        "error_code": exc.error_code,
        "sku": exc.sku,
        "requested_qty": exc.requested_qty,
        "available_qty": exc.available_qty,
        "is_paused": exc.is_paused,
        "is_planned": exc.is_planned,
        "planned_target_date": exc.planned_target_date,
        "substitutes": exc.substitutes,
    }


@extend_schema_view(
    get=extend_schema(
        tags=["storefront"],
        summary="Storefront menu projection",
        responses={200: OpenApiResponse(description="Catalog projection plus cart projection.")},
    ),
)
class StorefrontMenuView(APIView):
    """GET /api/v1/storefront/menu/"""

    permission_classes = [AllowAny]

    def get(self, request, collection: str | None = None):
        if collection is not None:
            catalog_service.ensure_active_collection(collection)
        catalog = build_catalog(
            channel_ref=STOREFRONT_CHANNEL_REF,
            collection_ref=collection,
            request=request,
        )
        return Response({
            "catalog": projection_data(catalog),
            "cart": _cart_payload(request),
        })


@extend_schema_view(
    get=extend_schema(
        tags=["storefront"],
        summary="Storefront product detail projection",
        responses={
            200: OpenApiResponse(description="Product detail projection plus cart projection."),
            404: DetailSerializer,
        },
    ),
)
class StorefrontProductView(APIView):
    """GET /api/v1/storefront/products/{sku}/"""

    permission_classes = [AllowAny]

    def get(self, request, sku: str):
        product = build_product_detail(
            sku=sku,
            channel_ref=STOREFRONT_CHANNEL_REF,
            request=request,
        )
        if product is None:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "product": projection_data(product),
            "cart": _cart_payload(request),
        })


@extend_schema_view(
    get=extend_schema(
        tags=["storefront"],
        summary="Storefront cart projection",
        responses={200: OpenApiResponse(description="Cart projection.")},
    ),
)
class StorefrontCartView(APIView):
    """GET /api/v1/storefront/cart/"""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"cart": _cart_payload(request)})


@extend_schema_view(
    put=extend_schema(
        tags=["cart"],
        summary="Set absolute cart quantity by SKU",
        request=SetSkuQtySerializer,
        responses={
            200: OpenApiResponse(description="Cart command response plus authoritative cart projection."),
            400: DetailSerializer,
            404: DetailSerializer,
            409: OpenApiResponse(description="Insufficient stock."),
        },
    ),
)
class CartSkuQtyView(APIView):
    """PUT /api/v1/cart/skus/{sku}/"""

    permission_classes = [AllowAny]
    serializer_class = SetSkuQtySerializer

    def put(self, request, sku: str):
        serializer = SetSkuQtySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            outcome = set_qty_by_sku(
                request,
                sku=sku.strip(),
                qty=serializer.validated_data["qty"],
            )
        except CartCommandNotFound:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        except CartCommandUnavailable as unavailable:
            return Response(
                _stock_error_payload(unavailable.stock_error),
                status=status.HTTP_409_CONFLICT,
            )

        command = dict(outcome.payload)
        summary = command.pop("cart")
        return Response({
            **command,
            "summary": summary,
            "cart": _cart_payload(request),
        })
