"""Delivery coverage quote — antecipação de zona (omotenashi).

Permite ao storefront saber, no instante em que o cliente confirma um
endereço de entrega, se a loja entrega ali e qual a taxa — em vez de só
descobrir no commit final do pedido. Leitura pura de ``DeliveryZone``; a
``DeliveryZoneRule`` continua sendo o gate autoritativo no commit.
"""

from __future__ import annotations

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.utils.monetary import format_money


@extend_schema_view(
    post=extend_schema(
        tags=["delivery"],
        summary="Cobertura e taxa de entrega para um endereço",
    ),
)
@method_decorator(
    ratelimit(key="user_or_ip", rate="60/m", method="POST", block=False),
    name="dispatch",
)
class DeliveryZoneQuoteView(APIView):
    """
    POST /api/v1/delivery/quote/

    Body: {"postal_code": "86010-000", "neighborhood": "Centro"}
    Retorna {covered, fee_q, fee_display} — fee_display "Grátis" quando 0.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        if getattr(request, "limited", False):
            return Response({"detail": "Muitas consultas. Aguarde um instante."}, status=429)

        data = request.data or {}
        postal_code = str(data.get("postal_code") or "").strip()
        neighborhood = str(data.get("neighborhood") or "").strip()
        if not postal_code and not neighborhood:
            return Response({"detail": "Informe CEP ou bairro."}, status=400)

        from shopman.storefront.models import DeliveryZone

        zone = DeliveryZone.match(postal_code=postal_code, neighborhood=neighborhood)
        if zone is None:
            return Response({"covered": False, "fee_q": None, "fee_display": None})

        return Response({
            "covered": True,
            "fee_q": zone.fee_q,
            "fee_display": "Grátis" if zone.fee_q == 0 else f"R$ {format_money(zone.fee_q)}",
        })
