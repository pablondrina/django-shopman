"""Storefront Tracking API — order status by authorized ref.

Consumes ``OrderTrackingProjection`` from the projection layer.
"""
from __future__ import annotations

import logging

from django.http import Http404
from django.utils import timezone
from django_ratelimit.core import is_ratelimited
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.services import remote_mutations
from shopman.storefront.projections.order_tracking import build_order_tracking
from shopman.storefront.services import orders as order_service

from .actions import retry_after_action
from .projections import projection_data
from .serializers import DetailSerializer, OrderTrackingSerializer

logger = logging.getLogger(__name__)


TRACKING_RATE_LIMIT_RETRY_SECONDS = 30


def _copy_title(key: str, fallback: str) -> str:
    try:
        entry = resolve_copy(key, moment="*", audience="*")
        return entry.title or fallback
    except Exception:
        logger.debug("tracking._copy_title degraded; using fallback", exc_info=True)
        return fallback


def _copy_message(key: str, fallback: str) -> str:
    try:
        entry = resolve_copy(key, moment="*", audience="*")
        return entry.message or fallback
    except Exception:
        logger.debug("tracking._copy_message degraded; using fallback", exc_info=True)
        return fallback


def _payment_gate_url(ref: str) -> str:
    return f"/pedido/{ref}/pagamento"


def _rate_limited_response(detail: str = "Muitas tentativas. Aguarde um instante.") -> Response:
    return Response(
        {
            "title": _copy_title("TRACKING_RATE_LIMIT_TITLE", "Atualização pausada por um instante"),
            "detail": detail,
            "error_code": "rate_limited",
            "retry_after_seconds": TRACKING_RATE_LIMIT_RETRY_SECONDS,
            "actions": [retry_after_action(TRACKING_RATE_LIMIT_RETRY_SECONDS)],
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
    fulfillments = (*proj.delivery_fulfillments, *proj.pickup_fulfillments)
    data["ref"] = proj.order_ref
    data["payment_status"] = proj.payment_status_label
    data["requires_payment_gate"] = requires_payment_gate
    data["payment_gate_url"] = _payment_gate_url(proj.order_ref) if requires_payment_gate else None
    data["fulfillments"] = [
        {
            "status": f.status,
            "status_label": f.status_label,
            "tracking_label": f.tracking_label,
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
            return Response(
                {
                    "title": _copy_title("TRACKING_NOT_FOUND_TITLE", "Pedido não encontrado"),
                    "detail": _copy_message(
                        "TRACKING_NOT_FOUND_MESSAGE",
                        "Confira o link do pedido ou fale com a equipe.",
                    ),
                },
                status=404,
            )

        order_service.resolve_timeouts_if_due(order)
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
            return Response(
                {
                    "title": _copy_title("TRACKING_NOT_FOUND_TITLE", "Pedido não encontrado"),
                    "detail": _copy_message(
                        "TRACKING_NOT_FOUND_MESSAGE",
                        "Confira o link do pedido ou fale com a equipe.",
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        key = remote_mutations.idempotency_key_from_request(
            request,
            fallback=f"cancel:{ref}",
        )

        def execute_cancel() -> tuple[dict, int]:
            if not order_service.can_cancel(order):
                return (
                    {
                        "detail": "Não é possível cancelar este pedido no status atual.",
                        "error_code": "order_not_cancellable",
                        "payment_status": order_service.payment_status(order),
                    },
                    status.HTTP_409_CONFLICT,
                )

            order_service.cancel(order)
            data = _tracking_payload(order)
            serializer = OrderTrackingSerializer(data)
            return dict(serializer.data), status.HTTP_200_OK

        try:
            result = remote_mutations.run_idempotent_mutation(
                scope=f"order-cancel:{ref}",
                key=key,
                execute=execute_cancel,
                cache_response=lambda _body, code: code < 400,
            )
        except remote_mutations.RemoteMutationInProgress:
            return Response(
                {"detail": "Cancelamento já está em andamento.", "error_code": "mutation_in_progress"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(result.response_body, status=result.response_code)


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
            return Response(
                {
                    "title": _copy_title("TRACKING_NOT_FOUND_TITLE", "Pedido não encontrado"),
                    "detail": _copy_message(
                        "TRACKING_NOT_FOUND_MESSAGE",
                        "Confira o link do pedido ou fale com a equipe.",
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            rating = int((request.data if hasattr(request, "data") else {}).get("rating"))
        except (TypeError, ValueError):
            rating = 0
        comment = str((request.data if hasattr(request, "data") else {}).get("comment") or "").strip()
        if rating < 1 or rating > 5:
            return Response({"detail": "Avaliação deve ficar entre 1 e 5."}, status=400)

        key = remote_mutations.idempotency_key_from_request(
            request,
            fallback=f"rate:{ref}",
        )

        def execute_rate() -> tuple[dict, int]:
            current_projection = build_order_tracking(order)
            can_rate = any(action.ref == "rate_order" and action.enabled for action in current_projection.actions)
            if not can_rate:
                return (
                    {
                        "detail": "Este pedido ainda não pode ser avaliado.",
                        "error_code": "order_not_rateable",
                    },
                    status.HTTP_409_CONFLICT,
                )

            data = order.data.copy() if isinstance(order.data, dict) else {}
            data["customer_rating"] = {
                "rating": rating,
                "comment": comment[:500],
                "submitted_at": timezone.now().isoformat(),
                "source": "storefront_nuxt",
            }
            order.data = data
            order.save(update_fields=["data"])
            return _tracking_payload(order), status.HTTP_200_OK

        try:
            result = remote_mutations.run_idempotent_mutation(
                scope=f"order-rate:{ref}",
                key=key,
                execute=execute_rate,
                cache_response=lambda _body, code: code < 400,
            )
        except remote_mutations.RemoteMutationInProgress:
            return Response(
                {"detail": "Avaliação já está em andamento.", "error_code": "mutation_in_progress"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(result.response_body, status=result.response_code)
