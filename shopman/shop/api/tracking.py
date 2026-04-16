"""Storefront Tracking API — order status by ref.

Consumes ``OrderTrackingProjection`` from the projection layer.
"""
from __future__ import annotations

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from shopman.orderman.models import Order

from shopman.shop.projections.order_tracking import build_order_tracking

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

        proj = build_order_tracking(order)

        data = {
            "ref": proj.ref,
            "status": proj.status,
            "status_label": proj.status_label,
            "total_display": proj.total_display,
            "timeline": [
                {
                    "label": e.label,
                    "event_type": e.event_type,
                    "timestamp_display": e.timestamp_display,
                }
                for e in proj.timeline
            ],
            "items": [
                {
                    "sku": it.sku,
                    "name": it.name,
                    "qty": it.qty,
                    "unit_price_display": it.unit_price_display,
                    "total_display": it.total_display,
                }
                for it in proj.items
            ],
            "fulfillments": [
                {
                    "status": f.status,
                    "status_label": f.status_label,
                    "tracking_code": f.tracking_code,
                    "tracking_url": f.tracking_url,
                    "carrier": f.carrier,
                    "dispatched_at": f.dispatched_at_display,
                    "delivered_at": f.delivered_at_display,
                }
                for f in proj.fulfillments
            ],
            "payment_status": proj.payment_status,
        }

        serializer = OrderTrackingSerializer(data)
        return Response(serializer.data)
