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

from shopman.shop.services import access as access_service
from shopman.shop.services import auth as auth_service
from shopman.storefront.constants import HAS_AUTH
from shopman.storefront.identity import get_authenticated_customer
from shopman.storefront.intents._phone import normalize_phone_input
from shopman.storefront.intents.auth import clean_display_name, needs_confirmation

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


def _access_link_redirect(metadata: dict | None) -> str:
    """Derive the Nuxt store destination from AccessLink metadata.

    The destination is owned by the backend (no client-supplied ``next``), so a
    magic link can only ever land on a safe in-store path.
    """
    from shopman.shop.services import storefront_links

    meta = metadata if isinstance(metadata, dict) else {}
    order_ref = str(meta.get("order_ref") or "")
    action = str(meta.get("action") or "")
    if order_ref:
        if action == "payment":
            return storefront_links.path_order_payment(order_ref)
        if action == "reorder":
            return storefront_links.path_order_history()
        return storefront_links.path_order_tracking(order_ref)
    # A destination folded into the token at creation (e.g. ManyChat → /checkout).
    # It was validated as a safe relative path when minted; re-check defensively.
    next_path = str(meta.get("next") or "")
    if next_path.startswith("/") and not next_path.startswith("//"):
        return next_path
    return storefront_links.path_account()


@method_decorator(ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch")
class AccessLinkExchangeView(APIView):
    """POST /api/v1/auth/access/ — exchange a magic-link token for a session.

    The customer clicks ``…/a?t=<token>`` on the store; the Nuxt page posts the
    token here (through the BFF), so the session cookie is established on the
    store host. Returns the session payload plus the backend-derived ``redirect``
    destination (from the token metadata).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Exchange a magic-link token for a session")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )

        payload = request.data if hasattr(request, "data") else {}
        token = str(payload.get("token") or payload.get("t") or "").strip()
        if not token:
            return Response({"detail": "Link inválido."}, status=status.HTTP_400_BAD_REQUEST)

        if not HAS_AUTH:
            return Response({"ok": True, "redirect": "/account", **_session_payload(None)})

        metadata = access_service.token_metadata(token)
        result = access_service.exchange_token(token, request)
        if not result.success:
            logger.warning("access_link_exchange_failed error=%s", getattr(result, "error", "?"))
            return Response(
                {"detail": "Este link expirou ou já foi usado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hasattr(request, "session"):
            request.session["origin_channel"] = access_service.resolve_origin(result)

        # Access link vindo do site: o código NB carregou a sacola anônima na metadata.
        # A in-app browser que abre o link é sessão nova (sem sacola), então adotamos a
        # ref — mas só se a sessão atual estiver vazia (não sobrescreve uma sacola local).
        cart_ref = str(metadata.get("cart_session_key") or "") if isinstance(metadata, dict) else ""
        if cart_ref and hasattr(request, "session") and not request.session.get("cart_session_key"):
            request.session["cart_session_key"] = cart_ref

        order_ref = str(metadata.get("order_ref") or "") if isinstance(metadata, dict) else ""
        if order_ref:
            from shopman.storefront.services import orders as order_service

            order_service.grant_order_access(request, order_ref)

        customer = None
        try:
            if result.customer:
                customer = auth_service.customer_by_uuid(result.customer.uuid)
        except Exception:
            logger.debug("access_link_exchange: customer lookup degraded", exc_info=True)

        payload = {
            "ok": True,
            "redirect": _access_link_redirect(metadata),
            **_session_payload(customer),
        }
        # Handoff do site que expirou: entrou logado, mas a sacola não veio. Avisamos com
        # gentileza (copy configurável), sem bloquear a entrada. Ver ACCESS-LINK-UNIFICATION.
        if isinstance(metadata, dict) and metadata.get("handoff_expired"):
            from shopman.shop.omotenashi import resolve_copy

            payload["handoff_expired"] = True
            payload["notice"] = resolve_copy("LOGIN_HANDOFF_EXPIRED", moment="*").message
        return Response(payload)


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
            # IP real (XFF rightmost, TRUSTED_PROXY_DEPTH): atrás do LB,
            # REMOTE_ADDR é o proxy e o gate de IP bloquearia todo mundo junto.
            ip_address=auth_service.client_ip(request),
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
            # Timeout transparente: a validade do código é pública (o código não).
            "code_expires_at": getattr(auth_result, "expires_at", None) or "",
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
