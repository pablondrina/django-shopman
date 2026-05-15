"""Storefront Account API — profile, addresses, order history.

Consumes projections from the projection layer where applicable.
"""
from __future__ import annotations

import json
import logging

from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.authentication import SessionAuthentication
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import account as account_service
from shopman.shop.services import devices as device_service
from shopman.storefront.projections.account import build_account
from shopman.storefront.intents.types import AddressIntent
from shopman.storefront.services import orders as order_service
from shopman.storefront.views.auth import get_authenticated_customer

from .serializers import (
    AddressSerializer,
    CustomerProfileSerializer,
    DetailSerializer,
    OrderHistoryItemSerializer,
)

logger = logging.getLogger(__name__)


def _client_ip(request) -> str:
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded or request.META.get("REMOTE_ADDR", "") or ""


def _fmt_dt(value) -> str:
    if not value:
        return ""
    try:
        return timezone.localtime(value).strftime("%d/%m/%Y às %H:%M")
    except Exception:
        return str(value)


def _serialize_device(device: dict) -> dict:
    return {
        "id": device.get("id"),
        "label": device.get("label") or "Dispositivo",
        "created_at": device.get("created_at").isoformat() if device.get("created_at") else None,
        "created_at_display": _fmt_dt(device.get("created_at")),
        "last_used_at": device.get("last_used_at").isoformat() if device.get("last_used_at") else None,
        "last_used_at_display": _fmt_dt(device.get("last_used_at")) or "Ainda não usado novamente",
        "location": device.get("location") or "",
        "is_current": bool(device.get("is_current")),
    }


def _serialize_address(addr) -> dict:
    return {
        "id": addr.pk,
        "label": getattr(addr, "display_label", addr.label),
        "formatted_address": addr.formatted_address,
        "complement": addr.complement or "",
        "delivery_instructions": addr.delivery_instructions or "",
        "is_default": addr.is_default,
        "route": getattr(addr, "route", "") or "",
        "street_number": getattr(addr, "street_number", "") or "",
        "neighborhood": getattr(addr, "neighborhood", "") or "",
        "city": getattr(addr, "city", "") or "",
        "state_code": getattr(addr, "state_code", "") or "",
        "postal_code": getattr(addr, "postal_code", "") or "",
        "latitude": getattr(addr, "latitude", None),
        "longitude": getattr(addr, "longitude", None),
        "place_id": getattr(addr, "place_id", None) or "",
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
            "first_name": customer.first_name or "",
            "last_name": customer.last_name or "",
            "phone": customer.phone,
            "email": getattr(customer, "email", None) or "",
            "birthday": customer.birthday.isoformat() if getattr(customer, "birthday", None) else "",
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
                "first_name": updated.first_name or "",
                "last_name": updated.last_name or "",
                "phone": updated.phone,
                "email": getattr(updated, "email", None) or "",
                "birthday": updated.birthday.isoformat() if getattr(updated, "birthday", None) else "",
            }).data
        )


class AccountSummaryView(APIView):
    """GET /api/v1/account/summary/ — customer memory projection for Nuxt."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["account"], summary="Customer account memory summary")
    def get(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)

        account = build_account(customer)
        last_order = account.recent_orders[0] if account.recent_orders else None
        loyalty = None
        if account.loyalty:
            loyalty = {
                "tier": account.loyalty.tier,
                "tier_display": account.loyalty.tier_display,
                "points_balance": account.loyalty.points_balance,
                "stamps_current": account.loyalty.stamps_current,
                "stamps_target": account.loyalty.stamps_target,
                "stamps_completed": account.loyalty.stamps_completed,
                "stamps_range": list(account.loyalty.stamps_range),
                "transactions": [
                    {
                        "points": txn.points,
                        "description": txn.description,
                        "date_display": txn.date_display,
                        "is_credit": txn.is_credit,
                    }
                    for txn in account.loyalty.transactions
                ],
            }

        return Response({
            "customer_first_name": account.customer_first_name,
            "recent_order_count": len(account.recent_orders),
            "active_order_count": order_service.active_order_count_for_customer(
                customer_ref=customer.ref,
                phone=customer.phone,
            ),
            "last_order": {
                "ref": last_order.ref,
                "created_at_display": last_order.created_at_display,
                "total_display": last_order.total_display,
                "status_label": last_order.status_label,
                "item_count": last_order.item_count,
            } if last_order else None,
            "loyalty": loyalty,
            "food_preferences": [
                {"key": pref.key, "label": pref.label, "is_active": pref.is_active}
                for pref in account.food_pref_options
            ],
            "notification_preferences": [
                {
                    "key": pref.key,
                    "label": pref.label,
                    "description": pref.description,
                    "enabled": pref.enabled,
                }
                for pref in account.notification_prefs
            ],
        })


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
        except Exception:  # pragma: no cover - defensive
            logger.exception("storefront_account_address_create_failed", extra={"customer_ref": customer.ref})
            return Response(
                {"detail": "Não foi possível salvar o endereço. Revise os dados e tente novamente."},
                status=400,
            )

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
        except Exception:  # pragma: no cover - defensive
            logger.exception(
                "storefront_account_address_update_failed",
                extra={"customer_ref": customer.ref, "address_id": pk},
            )
            return Response(
                {"detail": "Não foi possível atualizar o endereço. Revise os dados e tente novamente."},
                status=400,
            )

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

        filter_param = request.query_params.get("filter") or "todos"
        if filter_param not in {"todos", "ativos", "anteriores"}:
            filter_param = "todos"
        data = order_service.order_history_for_customer(
            customer_ref=customer.ref,
            phone=customer.phone,
            filter_param=filter_param,
            limit=50,
        )
        serializer = OrderHistoryItemSerializer(data, many=True)
        return Response(serializer.data)


class ActiveOrderCountView(APIView):
    """GET /api/v1/account/orders/active/ — compact badge count."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"count": 0})
        return Response({
            "count": order_service.active_order_count_for_customer(
                customer_ref=customer.ref,
                phone=customer.phone,
            )
        })


class FoodPreferenceToggleView(APIView):
    """POST /api/v1/account/preferences/food/ — toggle one food preference."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def post(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)
        key = str((request.data if hasattr(request, "data") else {}).get("key") or "").strip()
        valid_keys = {option_key for option_key, _label in account_service.FOOD_PREFERENCE_OPTIONS}
        if key not in valid_keys:
            return Response({"detail": "Preferência inválida."}, status=400)

        prefs = account_service.toggle_food_preference(customer.ref, key)
        return Response({
            "food_preferences": [
                {"key": pref.key, "label": pref.label, "is_active": pref.is_active}
                for pref in prefs
            ]
        })


class NotificationPreferenceToggleView(APIView):
    """POST /api/v1/account/preferences/notifications/ — toggle one channel consent."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def post(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)
        channel = str((request.data if hasattr(request, "data") else {}).get("channel") or "").strip()
        valid_channels = {key for key, _label, _description in account_service.NOTIFICATION_CHANNELS}
        if channel not in valid_channels:
            return Response({"detail": "Canal inválido."}, status=400)

        prefs = account_service.toggle_notification_consent(
            customer.ref,
            channel,
            ip_address=_client_ip(request),
        )
        return Response({
            "notification_preferences": [
                {
                    "key": pref.key,
                    "label": pref.label,
                    "description": pref.description,
                    "enabled": pref.enabled,
                }
                for pref in prefs
            ]
        })


class AccountDeviceListView(APIView):
    """GET/DELETE /api/v1/account/devices/ — trusted devices for current customer."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def get(self, request):
        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return Response({"detail": "Authentication required."}, status=401)
        devices = device_service.list_devices(
            customer_id=customer_info.uuid,
            raw_token=request.COOKIES.get(device_service.cookie_name()),
        )
        return Response({"devices": [_serialize_device(device) for device in devices]})

    def delete(self, request):
        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return Response({"detail": "Authentication required."}, status=401)
        revoked = device_service.revoke_all(customer_id=customer_info.uuid)
        response = Response({"revoked": revoked})
        response.delete_cookie(device_service.cookie_name())
        return response


class AccountDeviceDetailView(APIView):
    """DELETE /api/v1/account/devices/<uuid>/ — revoke one trusted device."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def delete(self, request, device_id: str):
        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return Response({"detail": "Authentication required."}, status=401)
        devices = device_service.list_devices(
            customer_id=customer_info.uuid,
            raw_token=request.COOKIES.get(device_service.cookie_name()),
        )
        current_ids = {str(device.get("id")) for device in devices if device.get("is_current")}
        error = device_service.revoke_device(customer_id=customer_info.uuid, device_id=device_id)
        if error:
            return Response({"detail": error}, status=400)
        response = Response({"revoked": True, "id": str(device_id)})
        if str(device_id) in current_ids:
            response.delete_cookie(device_service.cookie_name())
        return response


class AccountExportView(APIView):
    """GET /api/v1/account/export/ — customer data export JSON."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)
        payload = account_service.export_customer_data(customer)
        body = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
        response = HttpResponse(body, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="shopman-dados-cliente.json"'
        return response


class AccountDeleteView(APIView):
    """POST /api/v1/account/delete/ — anonymize customer account after explicit ack."""

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication]

    def post(self, request):
        customer = get_authenticated_customer(request)
        if not customer:
            return Response({"detail": "Authentication required."}, status=401)
        payload = request.data if hasattr(request, "data") else {}
        if not payload.get("acknowledged"):
            return Response({"detail": "Confirme a exclusão antes de continuar."}, status=400)

        original_ref, phone_hash = account_service.anonymize_customer(customer)
        if hasattr(request, "session"):
            request.session.flush()
        response = Response({
            "ok": True,
            "customer_ref": original_ref,
            "phone_hash": phone_hash,
        })
        response.delete_cookie(device_service.cookie_name())
        return response
