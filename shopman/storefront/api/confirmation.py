"""Storefront Order Confirmation API — o momento "pedido recebido" (celebração yoin).

Resgate do Balde C (COPY-BACKLOG-UNBUILT): a tela de confirmação existia em Django
(order_confirmation.html), removida no cutover headless. Aqui ela renasce headless,
reusando a projection de tracking (itens, total, ETA, share_text) + a copy
CONFIRMATION_* momento-aware. Celebração contida, não performática.
"""
from __future__ import annotations

import logging

from django.http import Http404
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.omotenashi import OmotenashiContext, resolve_copy
from shopman.storefront.presentation.order_tracking import build_order_tracking
from shopman.storefront.services import orders as order_service

from .projections import projection_data
from .serializers import DetailSerializer

logger = logging.getLogger(__name__)


class OrderConfirmationView(APIView):
    """GET /api/v1/orders/{ref}/confirmation/ — dados do momento de confirmação.

    Mesmo gate de acesso do tracking (sessão/cliente/staff). A tela decide o layout:
    com pagamento pendente fica enxuta (destaque no "Pagar agora"); senão, celebra
    com itens + acompanhar + compartilhar.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(tags=["orders"], summary="Order confirmation moment", responses={404: DetailSerializer})
    def get(self, request, ref: str):
        try:
            order = order_service.get_accessible_order(request, ref)
        except Http404:
            return Response({"detail": "Pedido não encontrado."}, status=404)

        omo = OmotenashiContext.from_request(request)

        def title(key: str, fallback: str) -> str:
            return resolve_copy(key, moment=omo.moment, audience=omo.audience).title or fallback

        def message(key: str, fallback: str) -> str:
            return resolve_copy(key, moment=omo.moment, audience=omo.audience).message or fallback

        proj = build_order_tracking(order)
        tdata = projection_data(proj)
        requires_payment = order_service.requires_payment_gate(order)

        return Response({
            "order_ref": proj.order_ref,
            "heading": title("CONFIRMATION_HEADING", "Pedido recebido"),
            "customer_name": omo.customer_name or "",
            "eta_prefix": message("CONFIRMATION_ETA_PREFIX", "Começamos a preparar"),
            "eta_display": proj.eta_display or "",
            # Encomenda (WP-D): a confirmação mostra o combinado no lugar do ETA.
            "is_preorder": proj.is_preorder,
            "when_prefix": message("CONFIRMATION_PREORDER_WHEN_PREFIX", "Pedido para"),
            "when_display": proj.when_display or "",
            "items_heading": title("CONFIRMATION_ITEMS_HEADING", "Você encomendou"),
            "items": tdata.get("items", []),
            "total_display": proj.total_display,
            "requires_payment_gate": requires_payment,
            "payment_url": f"/pedido/{proj.order_ref}/pagamento" if requires_payment else None,
            "tracking_url": f"/pedido/{proj.order_ref}",
            "track_cta": title("CONFIRMATION_TRACK_CTA", "Acompanhar pedido"),
            "share_cta": title("CONFIRMATION_SHARE_CTA", "Compartilhar"),
            "share_text": proj.share_text,
        })
