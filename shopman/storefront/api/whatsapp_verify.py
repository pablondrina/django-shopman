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
from django.http import Http404
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
        next_path = str((payload or {}).get("next") or "").strip()

        session_key = None
        if hasattr(request, "session"):
            if not request.session.session_key:
                request.session.save()
            session_key = request.session.session_key

        result = wa.start_verification(phone=phone, session_key=session_key, next_path=next_path)
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
                {"ok": False, "reason": "missing_token_or_phone", "return_url": wa.return_url()},
                status=status.HTTP_200_OK,
            )

        result = wa.confirm_verification(token=token, whatsapp_phone=phone, name=name)
        # Desfechos de negócio sempre 200 (o flag ``ok`` carrega o resultado, e
        # ``return_url`` acompanha os dois casos): plataformas S2S como o ManyChat
        # só leem o corpo em 2xx — assim a Condition sobre ``ok`` sempre dispara.
        # 401 fica reservado a falha de auth (checada no topo).
        return Response(result, status=status.HTTP_200_OK)


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


def whatsapp_events_view(request, token: str):
    """SSE stream do reverse-OTP — canal ``wa-verify-<token>``.

    Push instantâneo: quando o ManyChat confirma, o backend emite no canal e o
    navegador refaz o fetch canônico de /status (fonte da verdade, que casa a
    sessão e autentica). Espelha ``order_events_view``: autoriza up front e
    404 para quem não é a sessão de origem, para o ``EventSource`` falhar limpo
    (não reconecta) e o cliente cair no poll de fallback.
    """
    from django_eventstream.views import events as eventstream_view

    normalized = wa.normalize_token(token)
    data = wa.peek(normalized)
    if data is None:
        raise Http404

    # Bind de sessão: só a sessão que iniciou o fluxo escuta o canal. Sessão
    # ausente/diferente → 404 (mais estrito que o /status, porque aqui abriríamos
    # um stream de longa duração para quem não é a origem).
    stored_sk = str(data.get("session_key") or "")
    current_sk = getattr(getattr(request, "session", None), "session_key", None) or ""
    if stored_sk and stored_sk != current_sk:
        raise Http404

    return eventstream_view(request, **{"format-channels": ["wa-verify-{token}"], "token": normalized})
