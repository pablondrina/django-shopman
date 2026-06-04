"""Storefront auth session API for API-first storefront clients."""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import logout as django_logout
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import auth as auth_service
from shopman.storefront.constants import HAS_AUTH
from shopman.storefront.intents._phone import normalize_phone_input
from shopman.storefront.intents.auth import clean_display_name, needs_confirmation
from shopman.storefront.views.auth import get_authenticated_customer

logger = logging.getLogger(__name__)


SessionSerializer = inline_serializer(
    name="StorefrontAuthSession",
    fields={
        "is_authenticated": serializers.BooleanField(),
        "customer_ref": serializers.CharField(allow_blank=True),
        "customer_name": serializers.CharField(allow_blank=True),
        "customer_phone": serializers.CharField(allow_blank=True),
        "customer_email": serializers.CharField(allow_blank=True),
        "requires_welcome": serializers.BooleanField(),
        "welcome_suggested_name": serializers.CharField(allow_blank=True),
    },
)


def _session_payload(customer) -> dict:
    if not customer:
        return {
            "is_authenticated": False,
            "customer_ref": "",
            "customer_name": "",
            "customer_phone": "",
            "customer_email": "",
            "requires_welcome": False,
            "welcome_suggested_name": "",
        }

    customer_name = getattr(customer, "name", "") or ""
    return {
        "is_authenticated": True,
        "customer_ref": getattr(customer, "ref", "") or "",
        "customer_name": customer_name,
        "customer_phone": getattr(customer, "phone", "") or "",
        "customer_email": getattr(customer, "email", "") or "",
        "requires_welcome": needs_confirmation(customer_name),
        "welcome_suggested_name": clean_display_name(customer_name),
    }


class SessionView(APIView):
    """GET /api/v1/auth/session/ — current customer identity as JSON."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Current storefront session", responses={200: SessionSerializer})
    def get(self, request):
        customer = get_authenticated_customer(request)
        return Response(_session_payload(customer))


class LogoutView(APIView):
    """POST /api/v1/auth/logout/ — end Django auth session as JSON."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Logout storefront session", responses={200: SessionSerializer})
    def post(self, request):
        preserved = {}
        if hasattr(request, "session"):
            preserved = auth_service.preserved_session_values(request.session)

        django_logout(request)

        if hasattr(request, "session"):
            for key, value in preserved.items():
                request.session[key] = value

        response = Response(_session_payload(None))
        auth_service.revoke_current_device(request=request, response=response)
        return response


def _normalize_payload_phone(payload: dict) -> str:
    raw = (
        payload.get("phone_normalized")
        or payload.get("phone")
        or payload.get("target")
        or ""
    )
    raw = str(raw).strip()
    phone_region = str(payload.get("phone_region") or "BR")
    international = phone_region == "INTL" or (raw.startswith("+") and not raw.startswith("+55"))
    return normalize_phone_input(raw, international=international) or ""


def _delivery_response(delivery_method: str) -> dict:
    label = "SMS" if delivery_method == "sms" else "WhatsApp"
    doorman = getattr(settings, "DOORMAN", {}) or {}
    chain = doorman.get("DELIVERY_CHAIN", [])
    sender_class = str(doorman.get("MESSAGE_SENDER_CLASS") or "")
    return {
        "delivery_method": delivery_method,
        "delivery_label": label,
        "dev_console_hint": bool(
            getattr(settings, "DEBUG", False)
            and ("console" in chain or "ConsoleSender" in sender_class)
        ),
    }


def _debug_otp_allowed() -> bool:
    if getattr(settings, "DEBUG", False):
        return True
    environment = str(getattr(settings, "SHOPMAN_ENVIRONMENT", "production")).strip().lower()
    return bool(
        getattr(settings, "SHOPMAN_EXPOSE_DEBUG_OTP", False)
        and environment in {"development", "dev", "local", "staging"}
    )


def _debug_otp_response(auth_result=None) -> dict:
    if not _debug_otp_allowed():
        return {}
    code = str(getattr(auth_result, "debug_code", "") or "")
    if not code:
        return {}
    return {
        "debug_otp_code": code,
        "debug_otp_expires_at": getattr(auth_result, "expires_at", None) or "",
    }


@method_decorator(ratelimit(key="user_or_ip", rate="5/m", method="POST", block=False), name="dispatch")
class RequestCodeView(APIView):
    """POST /api/v1/auth/request-code/ — request OTP as JSON."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Request storefront OTP")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        payload = request.data if hasattr(request, "data") else {}
        phone = _normalize_payload_phone(payload)
        if not phone:
            return Response(
                {"detail": "Telefone inválido.", "field": "phone"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        delivery_method = str(payload.get("delivery_method") or "whatsapp").strip().lower()
        if delivery_method not in {"whatsapp", "sms"}:
            delivery_method = "whatsapp"

        if not HAS_AUTH:
            return Response({"ok": True, "phone": phone, **_delivery_response(delivery_method)})

        auth_result = auth_service.request_code(
            phone=phone,
            delivery_method=delivery_method,
            ip_address=request.META.get("REMOTE_ADDR"),
        )
        if not auth_result.success:
            return Response(
                {"detail": auth_service.request_code_error_message(auth_result)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        actual_method = getattr(auth_result, "delivery_method", None) or delivery_method
        return Response({
            "ok": True,
            "phone": phone,
            **_delivery_response(actual_method),
            **_debug_otp_response(auth_result),
        })


@method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch")
class DeviceCheckView(APIView):
    """POST /api/v1/auth/device-check/ — skip OTP when trusted-device cookie is valid."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Check trusted device for passwordless login")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        payload = request.data if hasattr(request, "data") else {}
        phone = _normalize_payload_phone(payload)
        if not phone:
            return Response(
                {"detail": "Telefone inválido.", "field": "phone"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not HAS_AUTH:
            return Response({"ok": True, "trusted": False, "phone": phone, **_session_payload(None)})

        customer = auth_service.trusted_device_login(request, phone=phone)
        if not customer:
            return Response({"ok": True, "trusted": False, "phone": phone, **_session_payload(None)})

        return Response({"ok": True, "trusted": True, "phone": phone, **_session_payload(customer)})


@method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch")
class VerifyCodeView(APIView):
    """POST /api/v1/auth/verify-code/ — verify OTP and create session as JSON."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Verify storefront OTP")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        payload = request.data if hasattr(request, "data") else {}
        phone = _normalize_payload_phone(payload)
        code_input = str(payload.get("code") or "").strip()
        code_digits = "".join(ch for ch in code_input if ch.isdigit())
        if not phone:
            return Response(
                {"detail": "Telefone inválido.", "field": "phone"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if len(code_digits) != 6:
            return Response(
                {"detail": "Informe os 6 números do código.", "field": "code"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not HAS_AUTH:
            return Response({"ok": True, "phone": phone, "customer_name": ""})

        auth_result = auth_service.verify_for_login(
            phone=phone,
            code_input=code_digits,
            request=request,
        )
        if not auth_result.success:
            return Response(
                {"detail": auth_service.verify_error_message(auth_result)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        customer = None
        try:
            customer = auth_service.customer_by_uuid(auth_result.customer.uuid)
        except Exception:
            logger.debug("auth.post degraded; using fallback", exc_info=True)
            customer = None

        session = _session_payload(customer)
        session["customer_name"] = auth_service.confirmed_customer_name(auth_result) or session["customer_name"]
        return Response({"ok": True, "phone": phone, **session})


class TrustDeviceView(APIView):
    """POST /api/v1/auth/trust-device/ — persist trusted-device cookie after OTP consent."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Trust current device for future storefront logins")
    def post(self, request):
        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return Response({"detail": "Authentication required."}, status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data if hasattr(request, "data") else {}
        trust_value = payload.get("trust", False)
        trust = trust_value is True or str(trust_value).strip().lower() in {"1", "true", "yes"}

        response = Response({"ok": True, "trusted": False})
        if trust:
            auth_service.trust_device(
                response=response,
                customer_id=customer_info.uuid,
                request=request,
            )
            response.data["trusted"] = True
        return response
