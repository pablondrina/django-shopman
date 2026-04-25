"""Storefront Account API — profile, addresses, order history.

Consumes projections from the projection layer where applicable.
"""
from __future__ import annotations

from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.storefront.services import orders as order_service
from shopman.storefront.views.auth import get_authenticated_customer

from .serializers import (
    AddressSerializer,
    CustomerProfileSerializer,
    OrderHistoryItemSerializer,
)


@extend_schema_view(
    get=extend_schema(tags=["account"], summary="Get customer profile"),
)
class ProfileView(APIView):
    """
    GET /api/v1/account/profile/

    Returns authenticated customer's profile.
    Auth: Django auth via AuthCustomerMiddleware.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)

        data = {
            "ref": customer.ref,
            "name": customer.name,
            "phone": customer.phone,
            "email": getattr(customer, "email", None) or "",
        }
        serializer = CustomerProfileSerializer(data)
        return Response(serializer.data)


@extend_schema_view(
    get=extend_schema(tags=["account"], summary="List customer addresses"),
)
class AddressListView(APIView):
    """
    GET /api/v1/account/addresses/

    Returns authenticated customer's addresses.
    Auth: Django auth via AuthCustomerMiddleware.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)

        addresses = customer.addresses.order_by("-is_default", "label")
        data = []
        for addr in addresses:
            data.append({
                "id": addr.pk,
                "label": getattr(addr, "display_label", addr.label),
                "formatted_address": addr.formatted_address,
                "complement": addr.complement or "",
                "delivery_instructions": addr.delivery_instructions or "",
                "is_default": addr.is_default,
            })
        serializer = AddressSerializer(data, many=True)
        return Response(serializer.data)


@extend_schema_view(
    get=extend_schema(tags=["account"], summary="Order history"),
)
class OrderHistoryView(APIView):
    """
    GET /api/v1/account/orders/

    Returns last 20 orders for the authenticated customer.
    Auth: Django auth via AuthCustomerMiddleware.
    """

    permission_classes = [AllowAny]

    def get(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)

        data = order_service.order_history_for_phone(customer.phone, limit=20)
        serializer = OrderHistoryItemSerializer(data, many=True)
        return Response(serializer.data)
