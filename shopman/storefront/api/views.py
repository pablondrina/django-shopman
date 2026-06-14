from __future__ import annotations

import logging

from django.utils import timezone
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.utils.phone import normalize_phone

from shopman.shop.projections import catalog_context
from shopman.shop.services import checkout as checkout_service
from shopman.shop.services import sessions as session_service
from shopman.storefront.cart import CHANNEL_REF, CartService
from shopman.storefront.presentation import get_channel_listing_ref
from shopman.storefront.services import catalog as catalog_service
from shopman.storefront.services import orders as order_service

from .serializers import (
    AddItemSerializer,
    CartSerializer,
    CheckoutResponseSerializer,
    CheckoutSerializer,
    DetailSerializer,
    UpdateItemSerializer,
)

logger = logging.getLogger(__name__)


CHECKOUT_RATE_LIMIT_RETRY_SECONDS = 60


def _cart_data(request):
    """Resolve the cart DATA projection for the current visitor.

    The REST surface serializes this directly (``CartSerializer``) — the
    headless contract reads the orchestrator read-side, not the legacy dict.
    """
    from shopman.shop.projections.cart import build_cart

    return build_cart(request.session.get("cart_session_key"), CHANNEL_REF)


def _stock_unit_count_label(qty: int) -> str:
    unit_word = "unidade disponível" if qty == 1 else "unidades disponíveis"
    return f"{qty} {unit_word}"


def _stock_error_detail(exc) -> str:
    available_qty = getattr(exc, "available_qty", None)
    if available_qty is not None and available_qty > 0:
        return f"Estoque disponível agora: {_stock_unit_count_label(available_qty)}."
    return "Sem estoque disponível para a quantidade solicitada."


@extend_schema_view(
    get=extend_schema(
        tags=["cart"],
        summary="Get cart",
        responses={200: CartSerializer},
    ),
)
class CartView(APIView):
    """
    GET /api/v1/cart/

    Returns the current cart contents.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = CartSerializer

    def get(self, request):
        cart = _cart_data(request)
        data = CartSerializer(cart).data
        return Response(data)


@method_decorator(ratelimit(key="user_or_ip", rate="120/m", method="POST", block=False), name="post")
class CartAddItemView(APIView):
    """
    POST /api/v1/cart/items/

    Add an item to the cart. Requires sku and optional qty.
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    serializer_class = AddItemSerializer

    @extend_schema(
        tags=["cart"],
        summary="Add cart item",
        request=AddItemSerializer,
        responses={
            201: CartSerializer,
            400: DetailSerializer,
            404: DetailSerializer,
            409: OpenApiResponse(description="Estoque insuficiente para a quantidade solicitada."),
        },
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde um instante."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
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

        price_q = catalog_context.price_q_for_product(product, listing_ref=get_channel_listing_ref())
        if price_q is None:
            return Response(
                {"detail": "No price available for this product."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        from shopman.shop.services.cart import CartUnavailableError

        try:
            CartService.add_item(
                request,
                sku,
                qty,
                price_q,
                is_d1=catalog_context.is_d1_only(product.sku, channel_ref=CHANNEL_REF),
            )
        except CartUnavailableError as exc:
            return Response(
                {
                    "detail": _stock_error_detail(exc),
                    "error_code": exc.error_code,
                    "sku": exc.sku,
                    "requested_qty": exc.requested_qty,
                    "available_qty": exc.available_qty,
                    "is_paused": exc.is_paused,
                    "substitutes": exc.substitutes,
                },
                status=status.HTTP_409_CONFLICT,
            )

        cart = _cart_data(request)
        data = CartSerializer(cart).data
        return Response(data, status=status.HTTP_201_CREATED)


@method_decorator(ratelimit(key="user_or_ip", rate="120/m", method="PATCH", block=False), name="patch")
@method_decorator(ratelimit(key="user_or_ip", rate="120/m", method="DELETE", block=False), name="delete")
class CartItemView(APIView):
    """
    PATCH /api/v1/cart/items/{line_id}/ — update quantity
    DELETE /api/v1/cart/items/{line_id}/ — remove item
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    serializer_class = UpdateItemSerializer

    @extend_schema(
        tags=["cart"],
        summary="Update cart item quantity",
        request=UpdateItemSerializer,
        responses={200: CartSerializer, 404: DetailSerializer},
    )
    def patch(self, request, line_id):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde um instante."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
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

        cart = _cart_data(request)
        data = CartSerializer(cart).data
        return Response(data)

    @extend_schema(
        tags=["cart"],
        summary="Remove cart item",
        responses={200: CartSerializer, 404: DetailSerializer},
    )
    def delete(self, request, line_id):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde um instante."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        try:
            CartService.remove_item(request, line_id)
        except ValueError:
            return Response(
                {"detail": "No active cart."},
                status=status.HTTP_404_NOT_FOUND,
            )

        cart = _cart_data(request)
        data = CartSerializer(cart).data
        return Response(data)


@method_decorator(ratelimit(key="user_or_ip", rate="3/m", method="POST", block=False), name="post")
class CheckoutView(APIView):
    """
    POST /api/v1/checkout/

    Commit the cart as an order.
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    serializer_class = CheckoutSerializer

    @extend_schema(
        tags=["checkout"],
        summary="Commit cart as order",
        request=CheckoutSerializer,
        responses={
            201: CheckoutResponseSerializer,
            400: DetailSerializer,
            429: DetailSerializer,
        },
    )
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {
                    "detail": "Muitas tentativas. Aguarde alguns minutos.",
                    "error_code": "rate_limited",
                    "retry_after_seconds": CHECKOUT_RATE_LIMIT_RETRY_SECONDS,
                },
                status=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(CHECKOUT_RATE_LIMIT_RETRY_SECONDS)},
            )

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Check cart has items
        cart = _cart_data(request)
        if cart.is_empty:
            return Response(
                {"detail": "Cart is empty."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session_key = cart.session_key
        name = serializer.validated_data["name"]
        phone_raw = serializer.validated_data["phone"]
        notes = serializer.validated_data.get("notes", "")
        fulfillment_type = serializer.validated_data.get("fulfillment_type", "pickup")
        delivery_address = serializer.validated_data.get("delivery_address", "")
        saved_address_id = serializer.validated_data.get("saved_address_id")
        delivery_address_structured = serializer.validated_data.get("delivery_address_structured") or {}
        delivery_complement = serializer.validated_data.get("delivery_complement", "")
        delivery_instructions = serializer.validated_data.get("delivery_instructions", "")
        delivery_date = serializer.validated_data.get("delivery_date", "")
        delivery_time_slot = serializer.validated_data.get("delivery_time_slot", "")
        payment_method = serializer.validated_data.get("payment_method", "")
        use_loyalty = serializer.validated_data.get("use_loyalty", False)
        idempotency_key = serializer.validated_data.get("idempotency_key") or session_service.new_idempotency_key()

        if fulfillment_type != "delivery":
            saved_address_id = None
            delivery_address = ""
            delivery_address_structured = {}
            delivery_complement = ""
            delivery_instructions = ""

        if not delivery_date and (fulfillment_type == "delivery" or delivery_time_slot):
            return Response(
                {"detail": "Escolha a data.", "field": "delivery_date"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard autoritativo: nunca confirmar pedido para um dia fechado
        # (fim de semana fora do expediente, feriado, férias coletivas). A UI
        # já evita oferecer, mas o commit não bloqueia data futura — então o
        # servidor é a última linha. Prometer dia fechado seria gravíssimo.
        if delivery_date:
            from datetime import date as _date

            from shopman.shop.services import business_calendar

            try:
                _parsed_date = _date.fromisoformat(delivery_date)
            except ValueError:
                _parsed_date = None
            if _parsed_date is not None and not business_calendar.is_open_on(_parsed_date):
                message = "Estamos fechados nesse dia. Escolha outra data."
                return Response(
                    {"detail": message, "field": "delivery_date", "errors": {"delivery_date": message}},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if fulfillment_type == "pickup":
            from shopman.storefront.services.pickup_slots import validate_pickup_slot_selection

            try:
                now_local = timezone.localtime().time().replace(second=0, microsecond=0)
            except (ValueError, KeyError):
                now_local = None
            slot_error = validate_pickup_slot_selection(
                delivery_time_slot,
                delivery_date=delivery_date,
                cart_skus=[str(line.sku) for line in cart.lines if line.sku],
                now=now_local,
            )
            if slot_error:
                return Response(
                    {
                        "detail": slot_error,
                        "field": "delivery_time_slot",
                        "errors": {"delivery_time_slot": slot_error},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if fulfillment_type == "delivery" and saved_address_id:
            saved_payload, saved_error = _saved_address_payload(request, saved_address_id)
            if saved_error:
                return Response(saved_error, status=status.HTTP_400_BAD_REQUEST)
            if saved_payload:
                delivery_address = delivery_address or saved_payload["formatted_address"]
                delivery_address_structured = {
                    **saved_payload["structured"],
                    **_clean_structured_address(delivery_address_structured),
                }

        if fulfillment_type == "delivery":
            structured = _clean_structured_address(delivery_address_structured)
            delivery_address = delivery_address or str(structured.get("formatted_address") or "")
            if not delivery_address.strip():
                return Response(
                    {
                        "detail": "Informe o endereço de entrega.",
                        "field": "delivery_address",
                        "errors": {"delivery_address": "Informe o endereço de entrega."},
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            delivery_address_structured = structured

        phone = normalize_phone(phone_raw) or phone_raw

        checkout_data = {
            "customer": {"name": name, "phone": phone},
            "fulfillment_type": fulfillment_type,
        }
        if notes:
            checkout_data["order_notes"] = notes
        if delivery_address:
            checkout_data["delivery_address"] = delivery_address
        if saved_address_id:
            checkout_data["saved_address_id"] = saved_address_id
        if fulfillment_type == "delivery":
            structured = _clean_structured_address(delivery_address_structured)
            if delivery_complement:
                structured["complement"] = delivery_complement
            if delivery_instructions:
                structured["delivery_instructions"] = delivery_instructions
            if structured:
                checkout_data["delivery_address_structured"] = structured
        if delivery_date:
            checkout_data["delivery_date"] = delivery_date
        if delivery_time_slot:
            checkout_data["delivery_time_slot"] = delivery_time_slot
        if payment_method in {"pix", "card"}:
            checkout_data["payment"] = {"method": payment_method}

        # Presente (entrega para terceiro) — integridade antes do commit.
        from shopman.storefront.intents.gift import build_gift_data

        gift_data, gift_errors = build_gift_data(
            is_gift=serializer.validated_data.get("is_gift", False),
            recipient_name=serializer.validated_data.get("recipient_name", ""),
            recipient_phone=serializer.validated_data.get("recipient_phone", ""),
            gift_message=serializer.validated_data.get("gift_message", ""),
        )
        if gift_errors:
            field, message = next(iter(gift_errors.items()))
            return Response(
                {"detail": message, "field": field, "errors": gift_errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if gift_data:
            checkout_data.update(gift_data)

        if use_loyalty:
            try:
                from shopman.shop.projections import checkout_context

                customer_info = getattr(request, "customer", None)
                loyalty_balance_q = checkout_context.loyalty_balance(
                    customer_info.uuid if customer_info else None
                )
                if loyalty_balance_q > 0:
                    checkout_data["loyalty"] = {"redeem_points_q": loyalty_balance_q}
            except Exception:
                logger.debug("views.post degraded; using fallback", exc_info=True)
                pass

        try:
            result = checkout_service.process(
                session_key=session_key,
                channel_ref=CHANNEL_REF,
                data=checkout_data,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            logger.debug("views.post degraded; using fallback", exc_info=True)
            mapped = checkout_service.map_checkout_error(exc)
            if mapped:
                field, message = next(iter(mapped.items()))
                return Response(
                    {"detail": message, "field": field, "errors": mapped},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            order_error = checkout_service.map_order_error(exc)
            if order_error is not None:
                return Response(
                    {
                        "detail": order_error.detail,
                        "error_code": order_error.error_code,
                        "context": order_error.context,
                    },
                    status=order_error.http_status,
                )
            raise

        # Clear cart
        order_service.grant_order_access(request, result.order_ref)
        request.session.pop("cart_session_key", None)
        next_url = f"/tracking/{result.order_ref}"
        if payment_method in {"pix", "card"}:
            next_url = f"/pedido/{result.order_ref}/pagamento"
            if payment_method == "pix" and checkout_service.starts_payment_after_store_confirmation(CHANNEL_REF):
                next_url = f"/tracking/{result.order_ref}"

        data = CheckoutResponseSerializer(
            {
                "order_ref": result.order_ref,
                "status": result.status,
                "next_url": next_url,
            }
        ).data
        return Response(data, status=status.HTTP_201_CREATED)


_STRUCTURED_ADDRESS_FIELDS = (
    "formatted_address",
    "route",
    "street_number",
    "neighborhood",
    "city",
    "state_code",
    "postal_code",
    "country",
    "country_code",
    "latitude",
    "longitude",
    "place_id",
    "complement",
    "delivery_instructions",
)


def _clean_structured_address(value: dict | None) -> dict:
    if not isinstance(value, dict):
        return {}
    cleaned: dict = {}
    for field in _STRUCTURED_ADDRESS_FIELDS:
        raw = value.get(field)
        if raw is None or raw == "":
            continue
        cleaned[field] = raw
    return cleaned


def _saved_address_payload(request, address_id: int | None) -> tuple[dict | None, dict | None]:
    if not address_id:
        return None, None
    from shopman.shop.services import account as account_service
    from shopman.storefront.views.auth import get_authenticated_customer

    customer = get_authenticated_customer(request)
    if not customer:
        return None, {"detail": "Entre novamente para usar este endereço.", "field": "saved_address_id"}
    if account_service.address_belongs_to_other_customer(customer.ref, address_id):
        return None, {"detail": "Endereço não encontrado.", "field": "saved_address_id"}
    address = account_service.get_address(customer.ref, address_id)
    if not address:
        return None, {"detail": "Endereço não encontrado.", "field": "saved_address_id"}
    structured = _clean_structured_address({
        "formatted_address": address.formatted_address,
        "route": getattr(address, "route", "") or "",
        "street_number": getattr(address, "street_number", "") or "",
        "neighborhood": getattr(address, "neighborhood", "") or "",
        "city": getattr(address, "city", "") or "",
        "state_code": getattr(address, "state_code", "") or "",
        "postal_code": getattr(address, "postal_code", "") or "",
        "latitude": getattr(address, "latitude", None),
        "longitude": getattr(address, "longitude", None),
        "place_id": getattr(address, "place_id", "") or "",
        "complement": getattr(address, "complement", "") or "",
        "delivery_instructions": getattr(address, "delivery_instructions", "") or "",
    })
    return {
        "formatted_address": address.formatted_address,
        "structured": structured,
    }, None
