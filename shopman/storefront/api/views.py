from __future__ import annotations

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.utils.phone import normalize_phone

from shopman.shop.services import checkout as checkout_service
from shopman.shop.services import sessions as session_service
from shopman.storefront.cart import CHANNEL_REF, CartService
from shopman.storefront.services import catalog as catalog_service
from shopman.storefront.services.product_cards import get_price_q, line_item_is_d1

from .serializers import (
    AddItemSerializer,
    CartSerializer,
    CheckoutResponseSerializer,
    CheckoutSerializer,
    UpdateItemSerializer,
)


class CartView(APIView):
    """
    GET /api/v1/cart/

    Returns the current cart contents.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        cart = CartService.get_cart(request)
        data = CartSerializer(cart).data
        return Response(data)


class CartAddItemView(APIView):
    """
    POST /api/v1/cart/items/

    Add an item to the cart. Requires sku and optional qty.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = AddItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sku = serializer.validated_data["sku"]
        qty = serializer.validated_data["qty"]

        product = catalog_service.get_sellable_published_product(sku)
        if product is None:
            return Response(
                {"detail": "Product not found or unavailable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        price_q = get_price_q(product)
        if price_q is None:
            return Response(
                {"detail": "No price available for this product."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from shopman.storefront.cart import CartUnavailableError

        try:
            CartService.add_item(
                request,
                sku,
                qty,
                price_q,
                is_d1=line_item_is_d1(product),
            )
        except CartUnavailableError as exc:
            return Response(
                {
                    "detail": "Insufficient stock.",
                    "error_code": exc.error_code,
                    "sku": exc.sku,
                    "requested_qty": exc.requested_qty,
                    "available_qty": exc.available_qty,
                    "is_paused": exc.is_paused,
                    "substitutes": exc.substitutes,
                },
                status=status.HTTP_409_CONFLICT,
            )

        cart = CartService.get_cart(request)
        data = CartSerializer(cart).data
        return Response(data, status=status.HTTP_201_CREATED)


class CartItemView(APIView):
    """
    PATCH /api/v1/cart/items/{line_id}/ — update quantity
    DELETE /api/v1/cart/items/{line_id}/ — remove item
    """

    permission_classes = [AllowAny]

    def patch(self, request, line_id):
        serializer = UpdateItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        qty = serializer.validated_data["qty"]

        try:
            CartService.update_qty(request, line_id, qty)
        except ValueError:
            return Response(
                {"detail": "No active cart."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cart = CartService.get_cart(request)
        data = CartSerializer(cart).data
        return Response(data)

    def delete(self, request, line_id):
        try:
            CartService.remove_item(request, line_id)
        except ValueError:
            return Response(
                {"detail": "No active cart."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cart = CartService.get_cart(request)
        data = CartSerializer(cart).data
        return Response(data)


@method_decorator(ratelimit(key="user_or_ip", rate="3/m", method="POST", block=False), name="post")
class CheckoutView(APIView):
    """
    POST /api/v1/checkout/

    Commit the cart as an order.
    """

    permission_classes = [AllowAny]

    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check cart has items
        cart = CartService.get_cart(request)
        if not cart.get("items"):
            return Response(
                {"detail": "Cart is empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_key = cart["session_key"]
        name = serializer.validated_data["name"]
        phone_raw = serializer.validated_data["phone"]
        notes = serializer.validated_data.get("notes", "")
        fulfillment_type = serializer.validated_data.get("fulfillment_type", "pickup")
        delivery_address = serializer.validated_data.get("delivery_address", "")

        phone = normalize_phone(phone_raw) or phone_raw

        checkout_data = {
            "customer": {"name": name, "phone": phone},
            "fulfillment_type": fulfillment_type,
        }
        if notes:
            checkout_data["order_notes"] = notes
        if delivery_address:
            checkout_data["delivery_address"] = delivery_address

        result = checkout_service.process(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            data=checkout_data,
            idempotency_key=session_service.new_idempotency_key(),
        )

        # Clear cart
        request.session.pop("cart_session_key", None)

        data = CheckoutResponseSerializer(
            {
                "order_ref": result.order_ref,
                "status": result.status,
            }
        ).data
        return Response(data, status=status.HTTP_201_CREATED)
