"""Storefront Tracking API — order status by authorized ref.

Consumes ``OrderTrackingProjection`` from the projection layer.
"""
from __future__ import annotations

from django.http import Http404
from django.utils import timezone
from django_ratelimit.core import is_ratelimited
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.authentication import SessionAuthentication
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.storefront.projections.order_tracking import build_order_tracking
from shopman.storefront.services import orders as order_service

from .projections import projection_data
from .serializers import DetailSerializer, OrderTrackingSerializer


TRACKING_RATE_LIMIT_RETRY_SECONDS = 30


def _payment_gate_url(ref: str) -> str:
    return f"/pedido/{ref}/pagamento"


def _rating_url(ref: str) -> str:
    return f"/api/v1/orders/{ref}/rate/"


def _rating_data(order) -> dict:
    data = order.data if isinstance(order.data, dict) else {}
    rating = data.get("customer_rating")
    return rating if isinstance(rating, dict) else {}


def _can_rate(order) -> bool:
    if order.status not in {"delivered", "completed"}:
        return False
    return not bool(_rating_data(order).get("rating"))


def _rate_limited_response(detail: str = "Muitas tentativas. Aguarde um instante.") -> Response:
    return Response(
        {
            "detail": detail,
            "error_code": "rate_limited",
            "retry_after_seconds": TRACKING_RATE_LIMIT_RETRY_SECONDS,
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={"Retry-After": str(TRACKING_RATE_LIMIT_RETRY_SECONDS)},
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


def _tracking_payload(order) -> dict:
    proj = build_order_tracking(order)
    data = projection_data(proj)
    requires_payment_gate = order_service.requires_payment_gate(order)
    can_rate = _can_rate(order)
    fulfillments = (*proj.delivery_fulfillments, *proj.pickup_fulfillments)
    data["ref"] = proj.order_ref
    data["payment_status"] = proj.payment_status_label
    data["requires_payment_gate"] = requires_payment_gate
    data["payment_gate_url"] = _payment_gate_url(proj.order_ref) if requires_payment_gate else None
    data["can_rate"] = can_rate
    data["rating_url"] = _rating_url(proj.order_ref) if can_rate else None
    data["fulfillments"] = [
        {
            "status": f.status,
            "status_label": f.status_label,
            "tracking_code": f.tracking_code,
            "tracking_url": f.tracking_url,
            "carrier": f.carrier,
            "dispatched_at": f.dispatched_at_display,
            "delivered_at": f.delivered_at_display,
        }
        for f in fulfillments
    ]
    return data


@extend_schema_view(
    get=extend_schema(
        tags=["tracking"],
        summary="Get order tracking by ref",
        responses={200: OrderTrackingSerializer, 404: DetailSerializer},
    ),
)
class OrderTrackingView(APIView):
    """
    GET /api/v1/tracking/{ref}/

    Returns order status, timeline, items, fulfillments, and payment status.
    Auth: same browser session/customer/staff gate as the HTML tracking page.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = OrderTrackingSerializer
    throttle_classes = []

    def get(self, request, ref: str):
        if _request_is_rate_limited(
            request,
            group="storefront-api-tracking",
            rate="120/m",
            method="GET",
        ):
            return _rate_limited_response("Muitas consultas de tracking. Aguarde um instante.")

        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Order not found."}, status=404)

        order_service.resolve_payment_timeout_if_due(order)
        data = _tracking_payload(order)
        serializer = OrderTrackingSerializer(data)
        return Response(serializer.data)


@extend_schema_view(
    post=extend_schema(
        tags=["tracking"],
        summary="Cancel order by ref",
        responses={
            200: OrderTrackingSerializer,
            404: DetailSerializer,
            409: OpenApiResponse(description="Order cannot be cancelled."),
        },
    ),
)
class OrderCancelView(APIView):
    """
    POST /api/v1/orders/{ref}/cancel/

    Cancels an accessible order only when the canonical customer cancellation
    policy allows it. Paid or uncertain payment states remain blocked.
    """

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    serializer_class = OrderTrackingSerializer
    throttle_classes = []

    def post(self, request, ref: str):
        if _request_is_rate_limited(
            request,
            group="storefront-api-order-cancel",
            rate="20/m",
            method="POST",
        ):
            return _rate_limited_response()
        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        if not order_service.can_cancel(order):
            return Response(
                {
                    "detail": "Não é possível cancelar este pedido no status atual.",
                    "error_code": "order_not_cancellable",
                    "payment_status": order_service.payment_status(order),
                },
                status=status.HTTP_409_CONFLICT,
            )

        order_service.cancel(order)
        data = _tracking_payload(order)
        serializer = OrderTrackingSerializer(data)
        return Response(serializer.data)


@extend_schema_view(
    post=extend_schema(
        tags=["tracking"],
        summary="Rate completed order by ref",
        responses={
            200: OpenApiResponse(description="Rating registered."),
            400: DetailSerializer,
            404: DetailSerializer,
            409: OpenApiResponse(description="Order cannot be rated."),
        },
    ),
)
class OrderRateView(APIView):
    """POST /api/v1/orders/{ref}/rate/ — register one customer rating."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]
    throttle_classes = []

    def post(self, request, ref: str):
        if _request_is_rate_limited(
            request,
            group="storefront-api-order-rate",
            rate="20/m",
            method="POST",
        ):
            return _rate_limited_response()
        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        if not _can_rate(order):
            return Response(
                {"detail": "Este pedido ainda não pode ser avaliado."},
                status=status.HTTP_409_CONFLICT,
            )

        try:
            rating = int((request.data if hasattr(request, "data") else {}).get("rating"))
        except (TypeError, ValueError):
            rating = 0
        comment = str((request.data if hasattr(request, "data") else {}).get("comment") or "").strip()
        if rating < 1 or rating > 5:
            return Response({"detail": "Avaliação deve ficar entre 1 e 5."}, status=400)

        data = order.data.copy() if isinstance(order.data, dict) else {}
        data["customer_rating"] = {
            "rating": rating,
            "comment": comment[:500],
            "submitted_at": timezone.now().isoformat(),
            "source": "storefront_nuxt",
        }
        order.data = data
        order.save(update_fields=["data"])
        return Response({"ok": True, "can_rate": False})
