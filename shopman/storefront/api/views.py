from __future__ import annotations

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.offerman.models import Product
from shopman.orderman.ids import generate_idempotency_key
from shopman.orderman.services.commit import CommitService
from shopman.utils.phone import normalize_phone

from shopman.storefront.cart import CHANNEL_REF, CartService
from shopman.storefront.views._helpers import _get_price_q, _line_item_is_d1

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

        try:
            product = Product.objects.get(sku=sku, is_published=True, is_sellable=True)
        except Product.DoesNotExist:
            return Response(
                {"detail": "Product not found or unavailable."},
                status=status.HTTP_404_NOT_FOUND,
            )

        price_q = _get_price_q(product)
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
                is_d1=_line_item_is_d1(product),
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

        # Set customer data on session
        from shopman.orderman.services.modify import ModifyService

        ops = [
            {"op": "set_data", "path": "customer.name", "value": name},
            {"op": "set_data", "path": "customer.phone", "value": phone},
            {"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type},
        ]
        if notes:
            ops.append({"op": "set_data", "path": "customer.notes", "value": notes})
        if delivery_address:
            ops.append({"op": "set_data", "path": "delivery_address", "value": delivery_address})

        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            ops=ops,
        )

        # Set session handle for customer tracking
        from shopman.orderman.models import Session

        session_obj = Session.objects.get(session_key=session_key)
        session_obj.handle_type = "phone"
        session_obj.handle_ref = phone
        session_obj.save(update_fields=["handle_type", "handle_ref"])

        # Commit
        idempotency_key = generate_idempotency_key()
        result = CommitService.commit(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            idempotency_key=idempotency_key,
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
