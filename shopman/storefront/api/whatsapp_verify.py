"""Endpoint do start leve do login por WhatsApp (fluxo access-link).

``start`` — POST público (rate-limited): guarda o contexto do site (sacola anônima +
destino) sob um código NB-XxXx e devolve o deep link ``wa.me`` pré-preenchido. O login
em si acontece pelo access link que o ManyChat devolve (``AccessLinkCreateView``), não
aqui — sem handshake, sem polling, sem SSE. Ver o serviço em
``shopman.shop.services.whatsapp_verify`` e o guia do Flow ManyChat em
docs/guides/whatsapp-access-link.md.
"""

from __future__ import annotations

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import whatsapp_verify as wa


@method_decorator(
    ratelimit(key="ip", rate="10/m", method="POST", block=False), name="dispatch"
)
class WhatsAppVerifyStartView(APIView):
    """POST /api/v1/auth/whatsapp/start/ — start leve do login por WhatsApp.

    Guarda o contexto do site (sacola anônima + destino) sob um código NB-XxXx e
    devolve o deep link pré-preenchido. Sem handshake/poll/SSE — o login acontece
    pelo access link que o ManyChat devolve. Ver ACCESS-LINK-UNIFICATION-PLAN.md.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(tags=["auth"], summary="Start WhatsApp login (access-link handoff)")
    def post(self, request):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde alguns minutos."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        payload = request.data if hasattr(request, "data") else {}
        next_path = str((payload or {}).get("next") or "").strip()
        cart_key = ""
        if hasattr(request, "session"):
            cart_key = str(request.session.get("cart_session_key") or "")

        result = wa.start_access_link(cart_session_key=cart_key, next_path=next_path)
        return Response(result)
