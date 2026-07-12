"""Thin conversation projection endpoint for WhatsApp/ManyChat adapters."""

from __future__ import annotations

from django.http import Http404
from django_ratelimit.core import is_ratelimited
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services.conversation import build_order_conversation
from shopman.storefront.services import orders as order_service

from .actions import retry_after_action
from .projections import projection_data
from .serializers import DetailSerializer, RemoteConversationSerializer

CONVERSATION_RATE_LIMIT_RETRY_SECONDS = 30


def _rate_limited_response() -> Response:
    return Response(
        {
            "detail": "Muitas consultas de conversa. Aguarde um instante.",
            "error_code": "rate_limited",
            "retry_after_seconds": CONVERSATION_RATE_LIMIT_RETRY_SECONDS,
            "actions": [retry_after_action(CONVERSATION_RATE_LIMIT_RETRY_SECONDS)],
        },
        status=429,
        headers={"Retry-After": str(CONVERSATION_RATE_LIMIT_RETRY_SECONDS)},
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


@extend_schema_view(
    get=extend_schema(
        tags=["conversation"],
        summary="Get order conversation projection",
        responses={200: RemoteConversationSerializer, 404: DetailSerializer, 429: OpenApiResponse(description="Rate limited.")},
    ),
)
class OrderConversationView(APIView):
    """GET /api/v1/orders/{ref}/conversation/"""

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = RemoteConversationSerializer
    throttle_classes = []

    def get(self, request, ref: str):
        if _request_is_rate_limited(
            request,
            group="storefront-api-order-conversation",
            rate="120/m",
            method="GET",
        ):
            return _rate_limited_response()

        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Pedido não encontrado."}, status=404)

        order_service.resolve_timeouts_if_due(order)
        channel_ref = str(request.query_params.get("channel_ref") or order.channel_ref or "whatsapp").strip()
        projection = build_order_conversation(order, channel_ref=channel_ref)
        serializer = RemoteConversationSerializer(projection_data(projection))
        return Response(serializer.data)
