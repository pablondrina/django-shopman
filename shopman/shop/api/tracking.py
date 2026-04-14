"""Storefront Tracking API — order status by ref."""
from __future__ import annotations

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.orderman.models import Order
from shopman.shop.services import payment as payment_svc
from shopman.shop.web.views.tracking import (
    STATUS_LABELS,
    _build_tracking_context,
)

from .serializers import OrderTrackingSerializer


@extend_schema_view(
    get=extend_schema(tags=["tracking"], summary="Get order tracking by ref"),
)
class OrderTrackingView(APIView):
    """
    GET /api/tracking/{ref}/

    Returns order status, timeline, items, fulfillments, and payment status.
    Auth: AllowAny (ref is opaque).
    """

    permission_classes = [AllowAny]

    def get(self, request, ref: str):
        try:
            order = Order.objects.get(ref=ref)
        except Order.DoesNotExist:
            return Response({"detail": "Order not found."}, status=404)

        ctx = _build_tracking_context(order)

        # Merge delivery + pickup fulfillments
        fulfillments = ctx.get("delivery_fulfillments", []) + ctx.get("pickup_fulfillments", [])

        payment_status = payment_svc.get_payment_status(order)

        data = {
            "ref": order.ref,
            "status": order.status,
            "status_label": STATUS_LABELS.get(order.status, order.status),
            "total_display": ctx["total_display"],
            "timeline": ctx["timeline"],
            "items": ctx["items"],
            "fulfillments": fulfillments,
            "payment_status": payment_status,
        }

        serializer = OrderTrackingSerializer(data)
        return Response(serializer.data)
