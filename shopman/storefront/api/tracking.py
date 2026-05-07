"""Storefront Tracking API — order status by authorized ref.

Consumes ``OrderTrackingProjection`` from the projection layer.
"""
from __future__ import annotations

from django.http import Http404
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.storefront.projections.order_tracking import build_order_tracking
from shopman.storefront.services import orders as order_service

from .serializers import DetailSerializer, OrderTrackingSerializer


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
    serializer_class = OrderTrackingSerializer

    @method_decorator(ratelimit(key="user_or_ip", rate="120/m", method="GET", block=True))
    def get(self, request, ref: str):
        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Order not found."}, status=404)

        proj = build_order_tracking(order)

        fulfillments = (*proj.delivery_fulfillments, *proj.pickup_fulfillments)
        data = {
            "ref": proj.order_ref,
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
                for f in fulfillments
            ],
            "payment_status": proj.payment_status_label,
        }

        serializer = OrderTrackingSerializer(data)
        return Response(serializer.data)
