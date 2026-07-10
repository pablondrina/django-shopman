"""API-first storefront surface endpoints.

These endpoints expose the same projection layer used by the Django templates,
so an alternate client can swap the outer surface without duplicating business
rules.
"""

from __future__ import annotations

import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from django_ratelimit.core import is_ratelimited
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.services import remote_mutations
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.presentation import (
    build_cart,
    build_catalog,
    build_checkout,
    build_home,
    build_product_detail,
    build_reorder_conflict,
)
from shopman.storefront.services import catalog as catalog_service
from shopman.storefront.services.cart_mutations import (
    CartMutationNotFound,
    CartMutationUnavailable,
    set_qty_by_sku,
)

from .actions import action_payload, retry_after_action
from .projections import projection_data
from .serializers import DetailSerializer, SetSkuQtySerializer

logger = logging.getLogger(__name__)


CART_RATE_LIMIT_RETRY_SECONDS = 30
REORDER_RATE_LIMIT_RETRY_SECONDS = 60


def _unit_count_label(qty: int) -> str:
    unit_word = "unidade disponível" if qty == 1 else "unidades disponíveis"
    return f"{qty} {unit_word}"


def _cart_payload(request) -> dict:
    cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
    return projection_data(cart)


def _stock_reason(exc) -> str:
    if getattr(exc, "is_paused", False):
        return "Item pausado pela casa no momento."
    if getattr(exc, "is_planned", False):
        return "Disponível por encomenda, com limite para esta data."
    available_qty = getattr(exc, "available_qty", None)
    if available_qty is not None and available_qty > 0:
        return f"Estoque disponível agora: {_unit_count_label(available_qty)}."
    return "Sem estoque disponível para a quantidade solicitada."


def _stock_error_payload(exc, *, product=None) -> dict:
    item_name = getattr(product, "name", None) or getattr(exc, "sku", "")
    reason = _stock_reason(exc)
    actions = [
        action_payload(
            ref="review_cart",
            kind="link",
            label="Revisar sacola",
            href="/cart",
            priority="secondary",
        ),
        action_payload(
            ref="continue_shopping",
            kind="link",
            label="Ver cardápio",
            href="/menu",
            priority="quiet",
        ),
    ]
    if exc.available_qty and exc.available_qty > 0:
        actions.insert(0, action_payload(
            ref="set_available_qty",
            kind="mutation",
            label=f"Usar {_unit_count_label(exc.available_qty)}",
            priority="primary",
            href=f"/api/v1/cart/skus/{exc.sku}/",
            method="PUT",
            payload_schema={
                "type": "object",
                "required": ["qty"],
                "properties": {
                    "qty": {"type": "integer", "const": exc.available_qty},
                },
            },
        ))
    return {
        "detail": reason,
        "title": "Revise este item",
        "error_code": exc.error_code,
        "sku": exc.sku,
        "name": item_name,
        "requested_qty": exc.requested_qty,
        "available_qty": exc.available_qty,
        "is_paused": exc.is_paused,
        "is_planned": exc.is_planned,
        "planned_target_date": exc.planned_target_date,
        # Pré-reserva: item planejado tem próximo lote conhecido. Enquadra a escassez
        # como oferta ("garantir o seu") em vez de só "esgotou". A reserva de fato é o
        # planned-hold que já existe no carrinho.
        "planned_offer_title": (
            resolve_copy("KINTSUGI_PLANNED_OFFER", moment="*", audience="*").title or "Já vem quentinho"
        ) if exc.is_planned else "",
        "planned_offer_message": (
            resolve_copy("KINTSUGI_PLANNED_OFFER", moment="*", audience="*").message
            or "Sai fresquinho no próximo lote. Quer garantir o seu?"
        ) if exc.is_planned else "",
        # Kintsugi: enquadra a escassez com voz acolhedora (registro, admin-configurável).
        # Pausado é diferente de esgotado — "voltamos em breve", não "acabou".
        "shortage_title": (
            resolve_copy("KINTSUGI_SHORTAGE_GENERIC", moment="*", audience="*").title
            or "Esgotou enquanto você escolhia"
        ),
        "paused_title": (
            resolve_copy("KINTSUGI_PAUSED_COPY", moment="*", audience="*").title or "Voltamos em breve!"
        ) if exc.is_paused else "",
        "paused_message": (
            resolve_copy("KINTSUGI_PAUSED_COPY", moment="*", audience="*").message
            or "Esse item está temporariamente fora do cardápio."
        ) if exc.is_paused else "",
        "substitutes_intro": (
            resolve_copy("KINTSUGI_SHORTAGE_SUBSTITUTES_INTRO", moment="*", audience="*").message
            or "Que tal um destes no lugar?"
        ),
        "substitutes": exc.substitutes,
        "actions": actions,
        "items": [
            {
                "sku": exc.sku,
                "name": item_name,
                "requested_qty": exc.requested_qty,
                "available_qty": exc.available_qty,
                "reason": reason,
            }
        ],
    }


def _rate_limited_response(*, detail: str, retry_after_seconds: int) -> Response:
    return Response(
        {
            "detail": detail,
            "error_code": "rate_limited",
            "retry_after_seconds": retry_after_seconds,
            "actions": [retry_after_action(retry_after_seconds)],
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(retry_after_seconds)},
    )


def _request_is_rate_limited(request, *, group: str, rate: str, method: str) -> bool:
    return bool(is_ratelimited(
        request=request,
        group=group,
        key="user_or_ip",
        rate=rate,
        method=method,
        increment=True,
    ))


def _skipped_reorder_items(skipped: list[str]) -> list[dict]:
    return [
        {
            "name": name,
            "reason": "Indisponível para recompra agora.",
        }
        for name in skipped
    ]


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
    authentication_classes = [SessionAuthentication]
    throttle_classes = []

    def post(self, request, ref: str):
        from shopman.storefront.cart import CartService
        from shopman.storefront.services import orders as order_service

        if _request_is_rate_limited(
            request,
            group="storefront-api-reorder",
            rate="20/m",
            method="POST",
        ):
            return _rate_limited_response(
                detail="Muitas tentativas de recompra. Aguarde um instante.",
                retry_after_seconds=REORDER_RATE_LIMIT_RETRY_SECONDS,
            )

        try:
            order = order_service.get_accessible_order(request, ref)
        except Exception:
            logger.debug("surface.post degraded; using fallback", exc_info=True)
            return Response({"detail": "Pedido não encontrado."}, status=status.HTTP_404_NOT_FOUND)

        if order is None:
            return Response({"detail": "Pedido não encontrado."}, status=status.HTTP_404_NOT_FOUND)

        mode = (request.data.get("mode") if hasattr(request, "data") else None) or ""
        mode = str(mode).strip().lower()
        cart_has_items = CartService.has_items(request)

        if cart_has_items and mode not in {"replace", "append"}:
            conflict = build_reorder_conflict(request, order, order_ref=ref)
            return Response(projection_data(conflict), status=status.HTTP_409_CONFLICT)

        key = remote_mutations.idempotency_key_from_request(
            request,
            fallback=f"reorder:{ref}:{mode or 'default'}",
        )

        def execute_reorder() -> tuple[dict, int]:
            if mode == "replace":
                CartService.clear(request)

            skipped = order_service.add_reorder_items(request, order, cart_service=CartService)
            return (
                {
                    "ok": True,
                    "skipped": skipped,
                    "skipped_items": _skipped_reorder_items(skipped),
                    "cart": _cart_payload(request),
                },
                status.HTTP_200_OK,
            )

        try:
            result = remote_mutations.run_idempotent_mutation(
                scope=f"order-reorder:{ref}",
                key=key,
                execute=execute_reorder,
            )
        except remote_mutations.RemoteMutationInProgress:
            return Response(
                {"detail": "Recompra já está em andamento.", "error_code": "mutation_in_progress"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(result.response_body, status=result.response_code)


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
    authentication_classes = [SessionAuthentication]

    ERROR_MESSAGES = {
        "empty_code": "Informe o código do cupom.",
        "no_cart": "Sacola vazia.",
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


_DRAFT_ADDRESS_FIELDS = (
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


@extend_schema_view(
    patch=extend_schema(
        tags=["checkout"],
        summary="Persist fulfillment + delivery address draft and re-resolve cart",
        responses={200: OpenApiResponse(description="Cart projection reflecting delivery fee/coverage.")},
    ),
)
class CheckoutDraftView(APIView):
    """PATCH /api/v1/checkout/draft/

    Grava o recebimento e o endereço de entrega escolhidos na sessão e re-roda
    os modifiers, para que a taxa de entrega (e a cobertura de zona) já apareçam
    no total *antes* do commit. Preview de leitura — nenhum pedido é criado; a
    ``DeliveryZoneRule`` segue como gate autoritativo no commit.
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def patch(self, request):
        from shopman.shop.services import cart as cart_service

        data = request.data or {}
        fulfillment_type = (data.get("fulfillment_type") or "pickup").strip()
        if fulfillment_type not in {"pickup", "delivery"}:
            fulfillment_type = "pickup"

        structured_raw = data.get("delivery_address_structured") or {}
        structured: dict = {}
        if isinstance(structured_raw, dict):
            for field in _DRAFT_ADDRESS_FIELDS:
                value = structured_raw.get(field)
                if value not in (None, ""):
                    structured[field] = value

        session_key = request.session.get("cart_session_key")
        if session_key:
            cart_service.set_delivery_draft(
                session_key=session_key,
                channel_ref=STOREFRONT_CHANNEL_REF,
                fulfillment_type=fulfillment_type,
                delivery_address_structured=structured,
            )
        return Response({"cart": _cart_payload(request)})


@extend_schema_view(
    patch=extend_schema(
        tags=["checkout"],
        summary="Toggle loyalty points redemption on the session",
        responses={200: OpenApiResponse(description="Cart projection reflecting the loyalty discount.")},
    ),
)
class CheckoutLoyaltyView(APIView):
    """PATCH /api/v1/checkout/loyalty/

    Liga/desliga o resgate de pontos NA SESSÃO (fonte única) e re-resolve o
    cart. Carrinho e checkout passam a refletir o mesmo estado — em vez de um
    flag de UI que diverge do desconto realmente aplicado. Ao ligar, o saldo é
    resolvido no servidor (não confia em valor do cliente).
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def patch(self, request):
        from shopman.shop.projections import checkout_context
        from shopman.shop.services import cart as cart_service

        data = request.data or {}
        enabled = bool(data.get("enabled"))

        redeem_q = 0
        if enabled:
            customer_info = getattr(request, "customer", None)
            if customer_info is not None:
                try:
                    redeem_q = checkout_context.loyalty_balance(customer_info.uuid)
                except Exception:
                    logger.debug("loyalty balance lookup degraded", exc_info=True)
                    redeem_q = 0

        session_key = request.session.get("cart_session_key")
        if session_key:
            cart_service.set_loyalty_redeem(
                session_key=session_key,
                channel_ref=STOREFRONT_CHANNEL_REF,
                redeem_q=redeem_q,
            )
        return Response({"cart": _cart_payload(request)})


@extend_schema_view(
    put=extend_schema(
        tags=["cart"],
        summary="Set absolute cart quantity by SKU",
        request=SetSkuQtySerializer,
        responses={
            200: OpenApiResponse(description="Cart mutation response plus authoritative cart projection."),
            400: DetailSerializer,
            404: DetailSerializer,
            409: OpenApiResponse(description="Estoque insuficiente para a quantidade solicitada."),
        },
    ),
)
class CartSkuQtyView(APIView):
    """PUT /api/v1/cart/skus/{sku}/"""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    serializer_class = SetSkuQtySerializer
    throttle_classes = []

    def put(self, request, sku: str):
        if _request_is_rate_limited(
            request,
            group="storefront-api-cart-sku-qty",
            rate="120/m",
            method="PUT",
        ):
            return _rate_limited_response(
                detail="Muitas alterações na sacola. Aguarde um instante.",
                retry_after_seconds=CART_RATE_LIMIT_RETRY_SECONDS,
            )

        serializer = SetSkuQtySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            outcome = set_qty_by_sku(
                request,
                sku=sku.strip(),
                qty=serializer.validated_data["qty"],
            )
        except CartMutationNotFound:
            return Response({"detail": "Product not found."}, status=status.HTTP_404_NOT_FOUND)
        except CartMutationUnavailable as unavailable:
            return Response(
                _stock_error_payload(unavailable.stock_error, product=unavailable.product),
                status=status.HTTP_409_CONFLICT,
            )

        mutation = dict(outcome.payload)
        summary = mutation.pop("cart")
        return Response({
            **mutation,
            "summary": summary,
            "cart": _cart_payload(request),
        })
