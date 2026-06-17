"""Availability API endpoint — public, no auth, cached."""

from __future__ import annotations

from decimal import Decimal

from django.core.cache import cache
from django.http import Http404
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import availability as avail_service
from shopman.storefront.api.serializers import AvailabilityResponseSerializer
from shopman.storefront.services import catalog as catalog_service


@extend_schema_view(
    get=extend_schema(
        tags=["availability"],
        summary="Get product availability",
        parameters=[
            OpenApiParameter("channel", str, description="Optional channel scope."),
        ],
        responses={200: AvailabilityResponseSerializer},
    ),
)
class AvailabilityView(APIView):
    """
    GET /api/v1/availability/<sku>/?channel=<channel_ref>

    Returns the current availability status for a SKU, optionally scoped
    to a channel (listing gate + channel-specific stock scope).

    Response:
        {
            "ok": bool,
            "available_qty": str,   # Decimal as string
            "badge_text": str,      # Human-readable label (pt-BR)
            "badge_class": str,     # CSS class for badge rendering
            "is_bundle": bool,
        }

    Cache TTL: 10 seconds per (sku, channel_ref).
    """

    authentication_classes = []
    permission_classes = []
    serializer_class = AvailabilityResponseSerializer

    def get(self, request, sku):
        if not catalog_service.product_exists(sku):
            raise Http404

        channel_ref = request.GET.get("channel")
        cache_key = f"availability:{sku}:{channel_ref or 'default'}"

        cached = cache.get(cache_key)
        if cached:
            return Response(cached)

        result = avail_service.check(sku, Decimal("1"), channel_ref=channel_ref)

        badge_text, badge_class = _badge_for(result)

        data = {
            "ok": result["ok"],
            "available_qty": str(result["available_qty"]),
            "badge_text": badge_text,
            "badge_class": badge_class,
            "is_bundle": result.get("is_bundle", False),
        }

        cache.set(cache_key, data, 10)
        return Response(data)


@method_decorator(
    ratelimit(key="user_or_ip", rate="10/m", method="POST", block=False), name="dispatch"
)
class StockAlertSubscribeView(APIView):
    """POST /api/v1/availability/<sku>/notify/ — "Me avise quando disponível".

    Aberto a cliente logado (usa o telefone da conta) ou anônimo (telefone no
    corpo). Registra uma assinatura pendente; o aviso dispara quando o SKU volta.
    """

    authentication_classes = [SessionAuthentication]
    permission_classes = [AllowAny]

    def post(self, request, sku):
        if getattr(request, "limited", False):
            return Response(
                {"detail": "Muitas tentativas. Aguarde um instante."},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        if not catalog_service.product_exists(sku):
            raise Http404

        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.identity import get_authenticated_customer
        from shopman.storefront.intents._phone import normalize_phone_input
        from shopman.storefront.services import stock_alerts

        customer = get_authenticated_customer(request)
        phone = normalize_phone_input(str(request.data.get("phone") or "")) or ""
        if customer is None and not phone:
            return Response(
                {"detail": "Informe um telefone para avisarmos quando voltar.", "field": "phone"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        channel_ref = request.GET.get("channel") or STOREFRONT_CHANNEL_REF
        sub = stock_alerts.subscribe(sku, channel_ref=channel_ref, customer=customer, phone=phone)
        if sub is None:
            return Response(
                {"detail": "Não foi possível registrar o aviso."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"ok": True})


def _badge_for(result: dict) -> tuple[str, str]:
    """Derive Portuguese badge text and CSS class from an availability result.

    Vocabulário canônico (AVAILABILITY-PLAN §2): qualquer estado que não seja
    "pode pedir agora" vira "Indisponível" — um único rótulo.
    """
    if result["ok"]:
        return "Disponível", "badge-available"
    return "Indisponível", "badge-unavailable"
