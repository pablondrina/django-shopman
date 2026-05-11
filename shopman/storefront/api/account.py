"""Storefront Account API — profile, addresses, order history.

Consumes projections from the projection layer where applicable.
"""
from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import account as account_service
from shopman.storefront.intents.types import AddressIntent
from shopman.storefront.services import orders as order_service
from shopman.storefront.views.auth import get_authenticated_customer

from .serializers import (
    AddressSerializer,
    CustomerProfileSerializer,
    DetailSerializer,
    OrderHistoryItemSerializer,
)


def _serialize_address(addr) -> dict:
    return {
        "id": addr.pk,
        "label": getattr(addr, "display_label", addr.label),
        "formatted_address": addr.formatted_address,
        "complement": addr.complement or "",
        "delivery_instructions": addr.delivery_instructions or "",
        "is_default": addr.is_default,
    }


def _intent_from_payload(payload: dict, base=None) -> AddressIntent:
    def _field(name: str, default: str = "") -> str:
        if name in payload:
            value = payload.get(name)
            return (str(value) if value is not None else default).strip()
        if base is not None:
            return (getattr(base, name, None) or default) or default
        return default

    coords_payload = payload.get("coordinates")
    coordinates = None
    if isinstance(coords_payload, list | tuple) and len(coords_payload) == 2:
        try:
            coordinates = (float(coords_payload[0]), float(coords_payload[1]))
        except (TypeError, ValueError):
            coordinates = None

    return AddressIntent(
        label=_field("label", "home") or "home",
        label_custom=_field("label_custom"),
        formatted_address=_field("formatted_address"),
        route=_field("route"),
        street_number=_field("street_number"),
        neighborhood=_field("neighborhood"),
        city=_field("city"),
        state_code=_field("state_code"),
        postal_code=_field("postal_code"),
        complement=_field("complement"),
        delivery_instructions=_field("delivery_instructions"),
        place_id=_field("place_id") or None,
        is_default=bool(payload.get("is_default", getattr(base, "is_default", False) if base else False)),
        coordinates=coordinates,
        is_verified=coordinates is not None,
    )


@extend_schema_view(
    get=extend_schema(
        tags=["account"],
        summary="Get customer profile",
        responses={200: CustomerProfileSerializer, 401: DetailSerializer},
    ),
    patch=extend_schema(
        tags=["account"],
        summary="Update customer profile",
        responses={200: CustomerProfileSerializer, 400: DetailSerializer, 401: DetailSerializer},
    ),
)
class ProfileView(APIView):
    """
    GET /api/v1/account/profile/  → customer profile.
    PATCH /api/v1/account/profile/ → update first_name / last_name / email / birthday.
    Auth: Django auth via AuthCustomerMiddleware.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = CustomerProfileSerializer

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

    def patch(self, request):
        from datetime import date as date_type

        from shopman.storefront.intents.types import ProfileUpdateIntent

        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)

        payload = request.data if hasattr(request, "data") else {}
        first_name = (payload.get("first_name") or "").strip()
        last_name = (payload.get("last_name") or "").strip()
        email = (payload.get("email") or "").strip()
        birthday_raw = (payload.get("birthday") or "").strip()
        if not first_name:
            return Response(
                {"detail": "Nome é obrigatório.", "field": "first_name"},
                status=400,
            )

        birthday = None
        if birthday_raw:
            try:
                birthday = date_type.fromisoformat(birthday_raw)
            except ValueError:
                birthday = None

        intent = ProfileUpdateIntent(
            first_name=first_name,
            last_name=last_name,
            email=email,
            birthday=birthday,
        )
        try:
            updated = account_service.update_profile(customer.ref, intent)
        except Exception as exc:  # pragma: no cover - defensive
            return Response({"detail": str(exc) or "Não foi possível atualizar."}, status=400)

        return Response(
            CustomerProfileSerializer({
                "ref": updated.ref,
                "name": updated.name,
                "phone": updated.phone,
                "email": getattr(updated, "email", None) or "",
            }).data
        )


@extend_schema_view(
    get=extend_schema(
        tags=["account"],
        summary="List customer addresses",
        responses={200: AddressSerializer(many=True), 401: DetailSerializer},
    ),
    post=extend_schema(
        tags=["account"],
        summary="Create address",
        responses={201: AddressSerializer, 400: DetailSerializer, 401: DetailSerializer},
    ),
)
class AddressListView(APIView):
    """
    GET/POST /api/v1/account/addresses/

    GET: Returns authenticated customer's addresses.
    POST: Creates a new address from JSON payload.
    Auth: Django auth via AuthCustomerMiddleware.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = AddressSerializer

    def get(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)

        addresses = customer.addresses.order_by("-is_default", "label")
        data = [_serialize_address(addr) for addr in addresses]
        serializer = AddressSerializer(data, many=True)
        return Response(serializer.data)

    def post(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)

        payload = request.data if hasattr(request, "data") else {}
        if not (payload.get("formatted_address") or "").strip():
            return Response(
                {"detail": "Endereço é obrigatório.", "field": "formatted_address"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        intent = _intent_from_payload(payload)
        try:
            created = account_service.add_address(customer.ref, intent)
        except Exception as exc:  # pragma: no cover - defensive
            return Response({"detail": str(exc) or "Não foi possível salvar o endereço."}, status=400)

        return Response(_serialize_address(created), status=status.HTTP_201_CREATED)


@extend_schema_view(
    patch=extend_schema(
        tags=["account"],
        summary="Update address",
        responses={200: AddressSerializer, 401: DetailSerializer, 404: DetailSerializer},
    ),
    delete=extend_schema(
        tags=["account"],
        summary="Delete address",
        responses={204: OpenApiResponse(description="Address deleted."), 401: DetailSerializer, 404: DetailSerializer},
    ),
    post=extend_schema(
        tags=["account"],
        summary="Set address as default",
        responses={200: AddressSerializer, 401: DetailSerializer, 404: DetailSerializer},
    ),
)
class AddressDetailView(APIView):
    """
    PATCH/DELETE/POST /api/v1/account/addresses/<pk>/

    PATCH: update address fields.
    DELETE: remove address.
    POST: set as default (when ?action=default).
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = AddressSerializer

    def patch(self, request, pk: int):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)
        if account_service.address_belongs_to_other_customer(customer.ref, pk):
            return Response({"detail": "Forbidden."}, status=403)
        addr = account_service.get_address(customer.ref, pk)
        if not addr:
            return Response({"detail": "Endereço não encontrado."}, status=404)

        payload = request.data if hasattr(request, "data") else {}
        intent = _intent_from_payload(payload, base=addr)
        try:
            account_service.update_address(customer.ref, pk, intent)
        except Exception as exc:  # pragma: no cover - defensive
            return Response({"detail": str(exc) or "Não foi possível atualizar o endereço."}, status=400)

        addr = account_service.get_address(customer.ref, pk)
        return Response(_serialize_address(addr))

    def delete(self, request, pk: int):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)
        if account_service.address_belongs_to_other_customer(customer.ref, pk):
            return Response({"detail": "Forbidden."}, status=403)
        if not account_service.get_address(customer.ref, pk):
            return Response({"detail": "Endereço não encontrado."}, status=404)

        account_service.delete_address(customer.ref, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)

    def post(self, request, pk: int):
        action = request.query_params.get("action") or request.data.get("action")
        if action != "default":
            return Response({"detail": "Use ?action=default."}, status=400)
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)
        if account_service.address_belongs_to_other_customer(customer.ref, pk):
            return Response({"detail": "Forbidden."}, status=403)
        if not account_service.get_address(customer.ref, pk):
            return Response({"detail": "Endereço não encontrado."}, status=404)

        account_service.set_default_address(customer.ref, pk)
        addr = account_service.get_address(customer.ref, pk)
        return Response(_serialize_address(addr))


@extend_schema_view(
    get=extend_schema(
        tags=["account"],
        summary="Order history",
        responses={200: OrderHistoryItemSerializer(many=True), 401: DetailSerializer},
    ),
)
class OrderHistoryView(APIView):
    """
    GET /api/v1/account/orders/

    Returns last 20 orders for the authenticated customer.
    Auth: Django auth via AuthCustomerMiddleware.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = OrderHistoryItemSerializer

    def get(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)

        data = order_service.order_history_for_phone(customer.phone, limit=20)
        serializer = OrderHistoryItemSerializer(data, many=True)
        return Response(serializer.data)
