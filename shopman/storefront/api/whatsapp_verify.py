"""Endpoints do reverse-OTP de WhatsApp (verificação de número via ManyChat).

Três superfícies:
  - ``start``   POST público (rate-limited): gera token + deep link wa.me.
  - ``confirm`` POST server-to-server (ManyChat → Django), autenticado pela
                DOORMAN_ACCESS_LINK_API_KEY. Marca o token como verificado.
  - ``status``  GET/POST público (rate-limited): polling; ao verificar,
                autentica a sessão do navegador e devolve o payload de sessão.

Ver o serviço em ``shopman.shop.services.whatsapp_verify`` e o guia de
configuração do Flow ManyChat em docs/guides/whatsapp-reverse-otp.md.
"""

from __future__ import annotations

import hmac
import logging

from django.conf import settings
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import whatsapp_verify as wa
from shopman.storefront.intents._phone import normalize_phone_input
from shopman.storefront.intents.auth import clean_display_name

from .auth import _session_payload

logger = logging.getLogger(__name__)


def _configured_api_key() -> str:
    doorman = getattr(settings, "DOORMAN", {}) or {}
    return str(doorman.get("ACCESS_LINK_API_KEY") or "")


def _presented_api_key(request) -> str:
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.META.get("HTTP_X_API_KEY", "").strip()


def _api_key_ok(request) -> bool:
    """Constant-time check da chave server-to-server. Fail-closed sem chave."""
    expected = _configured_api_key()
    if not expected:
        # Sem chave configurada: só permitir em DEBUG (dev). Fora disso, rejeita.
        return bool(getattr(settings, "DEBUG", False))
    presented = _presented_api_key(request)
    if not presented:
        return False
    return hmac.compare_digest(expected, presented)


@method_decorator(
    ratelimit(key="ip", rate="10/m", method="POST", block=False), name="dispatch"
)
class WhatsAppVerifyStartView(APIView):
    """POST /api/v1/auth/whatsapp/start/ — inicia verificação, devolve deep link."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Start WhatsApp number verification")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        payload = request.data if hasattr(request, "data") else {}
        raw_phone = str((payload or {}).get("phone") or "").strip()
        phone = normalize_phone_input(raw_phone) or "" if raw_phone else ""

        session_key = None
        if hasattr(request, "session"):
            if not request.session.session_key:
                request.session.save()
            session_key = request.session.session_key

        result = wa.start_verification(phone=phone, session_key=session_key)
        return Response(result)


class WhatsAppVerifyConfirmView(APIView):
    """POST /api/v1/auth/whatsapp/confirm/ — callback S2S do ManyChat."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Confirm WhatsApp verification (server-to-server)")
    def post(self, request):
        if not _api_key_ok(request):
            logger.warning("wa_verify.confirm unauthorized")
            return Response({"detail": "unauthorized"}, status=status.HTTP_401_UNAUTHORIZED)

        payload = request.data if hasattr(request, "data") else {}
        payload = payload or {}
        token = str(payload.get("token") or "").strip()
        phone = str(payload.get("phone") or payload.get("whatsapp_phone") or "").strip()
        name = str(
            payload.get("name")
            or " ".join(
                p for p in [str(payload.get("first_name") or ""), str(payload.get("last_name") or "")] if p
            )
            or ""
        ).strip()
        if not token or not phone:
            return Response(
                {"detail": "token e phone são obrigatórios."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = wa.confirm_verification(token=token, whatsapp_phone=phone, name=name)
        code = status.HTTP_200_OK if result.get("ok") else status.HTTP_404_NOT_FOUND
        return Response(result, status=code)


@method_decorator(
    ratelimit(key="ip", rate="30/m", method=["GET", "POST"], block=False),
    name="dispatch",
)
class WhatsAppVerifyStatusView(APIView):
    """GET|POST /api/v1/auth/whatsapp/status/ — polling do status + login."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Poll WhatsApp verification status")
    def get(self, request):
        return self._respond(request, request.GET.get("token", "").strip())

    def post(self, request):
        payload = request.data if hasattr(request, "data") else {}
        token = str((payload or {}).get("token") or "").strip()
        return self._respond(request, token)

    def _respond(self, request, token: str):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not token:
            return Response({"status": "expired", **_session_payload(None)})

        result = wa.verification_status(token=token, request=request)
        verification_status = result.get("status")
        customer = result.get("customer") if verification_status == "verified" else None
        payload = {"status": verification_status, **_session_payload(customer)}

        if verification_status == "verified":
            # Traz o nome do perfil do WhatsApp como sugestão para o cliente
            # confirmar ("Como quer ser chamado?"), sem gravá-lo como definitivo.
            suggested = clean_display_name(result.get("suggested_name") or "")
            if suggested and (payload.get("requires_welcome") or result.get("created")):
                payload["welcome_suggested_name"] = suggested
                payload["requires_welcome"] = True
            if result.get("phone_mismatch"):
                payload["phone_mismatch"] = True

        return Response(payload)
