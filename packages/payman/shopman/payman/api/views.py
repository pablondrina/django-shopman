from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ReadOnlyModelViewSet
from shopman.payman.models.intent import PaymentIntent
from shopman.payman.service import PaymentService

from .serializers import PaymentIntentListSerializer, PaymentIntentSerializer


class PaymentIntentViewSet(ReadOnlyModelViewSet):
    """Read-only ViewSet for payment intents."""

    permission_classes = [IsAuthenticated]
    lookup_field = "ref"

    def get_serializer_class(self):
        if self.action == "retrieve":
            return PaymentIntentSerializer
        return PaymentIntentListSerializer

    def get_queryset(self):
        qs = PaymentIntent.objects.all()
        order_ref = self.request.query_params.get("order_ref")
        if order_ref:
            qs = qs.filter(order_ref=order_ref)
        return qs.prefetch_related("transactions")


class ActiveIntentView(APIView):
    """
    GET /api/payments/active/?order_ref=ORD-001

    Get the most recent non-terminal intent for an order.
    """

    permission_classes = [IsAuthenticated]
    serializer_class = PaymentIntentSerializer

    @extend_schema(
        tags=["payments"],
        summary="Get active payment intent",
        parameters=[
            OpenApiParameter("order_ref", str, required=True),
        ],
        responses={200: PaymentIntentSerializer},
    )
    def get(self, request):
        order_ref = request.query_params.get("order_ref")
        if not order_ref:
            return Response(
                {"detail": "order_ref query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        intent = PaymentService.get_active_intent(order_ref)
        if not intent:
            return Response(
                {"detail": "No active intent for this order."},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = PaymentIntentSerializer(intent).data
        return Response(data)
