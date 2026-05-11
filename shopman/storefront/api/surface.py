"""API-first storefront surface endpoints.

These endpoints expose the same projection layer used by the Django templates,
so an alternate client can swap the outer surface without duplicating business
rules.
"""

from __future__ import annotations

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.projections import (
    build_cart,
    build_catalog,
    build_checkout,
    build_home,
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
        summary="Storefront home projection",
        responses={200: OpenApiResponse(description="Home projection plus cart projection.")},
    ),
)
@method_decorator(ensure_csrf_cookie, name="dispatch")
class StorefrontHomeView(APIView):
    """GET /api/v1/storefront/home/"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        home = build_home(request=request)
        return Response({
            "home": projection_data(home),
            "cart": _cart_payload(request),
        })


@extend_schema_view(
    get=extend_schema(
        tags=["storefront"],
        summary="Storefront menu projection",
        responses={200: OpenApiResponse(description="Catalog projection plus cart projection.")},
    ),
)
@method_decorator(ensure_csrf_cookie, name="dispatch")
class StorefrontMenuView(APIView):
    """GET /api/v1/storefront/menu/"""

    permission_classes = [AllowAny]
    authentication_classes = []

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
@method_decorator(ensure_csrf_cookie, name="dispatch")
class StorefrontProductView(APIView):
    """GET /api/v1/storefront/products/{sku}/"""

    permission_classes = [AllowAny]
    authentication_classes = []

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
@method_decorator(ensure_csrf_cookie, name="dispatch")
class StorefrontCartView(APIView):
    """GET /api/v1/storefront/cart/"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"cart": _cart_payload(request)})


@extend_schema_view(
    get=extend_schema(
        tags=["storefront"],
        summary="Storefront checkout projection",
        responses={200: OpenApiResponse(description="Checkout projection for API-first storefront clients.")},
    ),
)
@method_decorator(ensure_csrf_cookie, name="dispatch")
class StorefrontCheckoutView(APIView):
    """GET /api/v1/storefront/checkout/"""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        checkout = build_checkout(
            request=request,
            channel_ref=STOREFRONT_CHANNEL_REF,
        )
        return Response({"checkout": projection_data(checkout)})


@extend_schema_view(
    post=extend_schema(
        tags=["orders"],
        summary="Reorder past order",
        responses={
            200: OpenApiResponse(description="Items added to cart."),
            404: DetailSerializer,
            409: OpenApiResponse(description="Cart has items; client must choose mode."),
        },
    ),
)
class OrderReorderView(APIView):
    """POST /api/v1/orders/<ref>/reorder/

    Body: { "mode": "replace" | "append" } (optional on first call).

    Returns 409 if cart has items and no mode is specified; the client should
    show a conflict modal and resubmit with the chosen mode.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, ref: str):
        from shopman.storefront.cart import CartService
        from shopman.storefront.services import orders as order_service

        try:
            order = order_service.get_accessible_order(request, ref)
        except Exception:
            return Response({"detail": "Pedido não encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=status.HTTP_404_NOT_FOUND)

        mode = (request.data.get("mode") if hasattr(request, "data") else None) or ""
        mode = str(mode).strip().lower()
        cart_has_items = CartService.has_items(request)

        if cart_has_items and mode not in {"replace", "append"}:
            snapshot_items = (order.snapshot or {}).get("items") or []
            return Response(
                {
                    "detail": "Carrinho não está vazio. Escolha como continuar.",
                    "error_code": "cart_not_empty",
                    "order_ref": ref,
                    "items": [
                        {
                            "sku": item.get("sku"),
                            "name": item.get("name"),
                            "qty": int(item.get("qty", 1) or 1),
                        }
                        for item in snapshot_items
                        if item.get("sku")
                    ],
                },
                status=status.HTTP_409_CONFLICT,
            )

        if mode == "replace":
            CartService.clear(request)

        skipped = order_service.add_reorder_items(request, order, cart_service=CartService)
        return Response({
            "ok": True,
            "skipped": skipped,
            "cart": _cart_payload(request),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["cart"],
        summary="Apply coupon code",
        responses={
            200: OpenApiResponse(description="Cart projection after coupon applied."),
            400: DetailSerializer,
        },
    ),
    delete=extend_schema(
        tags=["cart"],
        summary="Remove coupon",
        responses={200: OpenApiResponse(description="Cart projection after coupon removed.")},
    ),
)
class CartCouponView(APIView):
    """POST/DELETE /api/v1/cart/coupon/"""

    permission_classes = [AllowAny]
    authentication_classes = []

    ERROR_MESSAGES = {
        "empty_code": "Informe o código do cupom.",
        "no_cart": "Carrinho vazio.",
        "invalid_coupon": "Cupom não encontrado.",
        "coupon_exhausted": "Este cupom já foi utilizado.",
        "coupon_expired": "Cupom expirado.",
    }

    def post(self, request):
        from shopman.storefront.cart import CartService

        code = (request.data.get("code") or "").strip() if hasattr(request, "data") else ""
        if not code:
            return Response(
                {"detail": self.ERROR_MESSAGES["empty_code"], "error_code": "empty_code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = CartService.apply_coupon(request, code)
        if result.get("ok"):
            return Response({"cart": _cart_payload(request)})

        error_key = result.get("error", "invalid_coupon")
        return Response(
            {
                "detail": self.ERROR_MESSAGES.get(error_key, "Cupom inválido."),
                "error_code": error_key,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    def delete(self, request):
        from shopman.storefront.cart import CartService

        CartService.remove_coupon(request)
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
    authentication_classes = []
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
