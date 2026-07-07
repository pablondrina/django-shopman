"""Machine webhook — push de status/posição das corridas de entrega.

Cadastrado na Machine via ``manage.py machine_register_webhook`` (tipos
``status`` e ``posicao``, responsabilidade ``solicitante``). Autenticação por
token compartilhado (``SHOPMAN_MACHINE["webhook_token"]``) no header
``X-Machine-Webhook-Token`` ou no query param ``?token=`` — a URL cadastrada
na Machine leva o token no query param. Token ausente/errado → 401 fail-closed
em qualquer ambiente (mesmo contrato do EFI, ver ``efi.py``).

⚠️ O payload do EVENTO não é documentado na collection da Machine — só o
cadastro do webhook. O parsing é defensivo (múltiplas chaves candidatas) e o
corpo cru é SEMPRE logado; o polling (``courier.sync``) é a via garantida
enquanto o formato real não for observado em homologação. Payload não
reconhecido → 202 (não punimos a Machine por um formato que ainda não
conhecemos; nada é perdido — o polling converge).

Status converge no funil ``courier.apply_status`` (idempotente — replay do
mesmo status é no-op). Posição não toca o Order: vai para o cache
(``courier:pos:{id_mch}``, TTL 120s), lida pela projection do gestor.
"""

from __future__ import annotations

import hmac
import logging

from django.conf import settings
from django.core.cache import cache
from drf_spectacular.utils import extend_schema
from rest_framework import status as http
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.services import webhook_idempotency

logger = logging.getLogger(__name__)

#: Chaves candidatas ao id da corrida no evento (formato não documentado).
_ID_KEYS = ("id_mch", "id", "solicitacao_id", "id_solicitacao", "request_id")

#: Chaves candidatas ao status.
_STATUS_KEYS = ("status", "status_solicitacao", "situacao")

POSITION_CACHE_SECONDS = 120


def _cfg() -> dict:
    return getattr(settings, "SHOPMAN_MACHINE", {}) or {}


@extend_schema(exclude=True)
class MachineWebhookView(APIView):
    """Endpoint para eventos de corrida (status/posição) da Machine."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        # Health probe do cadastro; a autenticação vale igual.
        if not self._check_auth(request):
            return Response({"error": "Unauthorized"}, status=http.HTTP_401_UNAUTHORIZED)
        return Response(status=http.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        if not self._check_auth(request):
            return Response({"error": "Unauthorized"}, status=http.HTTP_401_UNAUTHORIZED)

        raw = request.body[:2000] if isinstance(request.body, bytes) else b""
        logger.info("machine.webhook raw=%s", raw.decode("utf-8", errors="replace"))

        event = request.data if isinstance(request.data, dict) else {}
        ride_ref = _first(event, _ID_KEYS)
        if not ride_ref:
            # Formato desconhecido: aceito (202) + logado; o polling converge.
            return Response({"status": "unrecognized"}, status=http.HTTP_202_ACCEPTED)

        lat, lng = event.get("lat"), event.get("lng")
        if lat is None:
            lat = event.get("lat_condutor")
        if lng is None:
            lng = event.get("lng_condutor")
        if lat is not None and lng is not None:
            cache.set(
                f"courier:pos:{ride_ref}",
                {"lat": str(lat), "lng": str(lng)},
                POSITION_CACHE_SECONDS,
            )

        ride_status = _first(event, _STATUS_KEYS).upper()
        if not ride_status:
            # Evento só de posição: cache atualizado acima, nada mais a fazer.
            return Response({"status": "ok", "kind": "position"}, status=http.HTTP_200_OK)

        from shopman.orderman.models import Order

        order = Order.objects.filter(data__courier__id_mch=str(ride_ref)).first()
        if order is None:
            logger.warning("machine.webhook: corrida sem pedido id_mch=%s", ride_ref)
            return Response({"status": "ok", "kind": "unknown_ride"}, status=http.HTTP_200_OK)

        claim = webhook_idempotency.claim(
            "webhook:machine",
            webhook_idempotency.stable_webhook_key(ride_ref, ride_status),
        )
        if claim.replayed:
            return Response({"status": "ok", "kind": "replay"}, status=http.HTTP_200_OK)
        if claim.in_progress:
            return Response(claim.response_body, status=http.HTTP_409_CONFLICT)

        try:
            from shopman.shop.services import courier

            courier.apply_status(order, ride_status, source="webhook", details=event)
            webhook_idempotency.mark_done(
                claim,
                response_body={"status": "processed", "id_mch": str(ride_ref), "ride_status": ride_status},
            )
        except Exception as exc:
            webhook_idempotency.mark_failed(claim)
            from shopman.shop.services import observability

            observability.record_webhook_failure(
                provider="machine",
                reason="processing_failed",
                status_code=http.HTTP_500_INTERNAL_SERVER_ERROR,
                external_ref=str(ride_ref),
                exc=exc,
                context={"id_mch": str(ride_ref), "ride_status": ride_status},
            )
            logger.exception("MachineWebhook: error processing id_mch=%s", ride_ref)
            # 5xx → a Machine (se reentregar) tenta de novo; o polling cobre se não.
            return Response({"status": "retry"}, status=http.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({"status": "ok", "kind": "status"}, status=http.HTTP_200_OK)

    def _check_auth(self, request: Request) -> bool:
        expected = _cfg().get("webhook_token") or ""
        if not expected:
            logger.error(
                "MachineWebhook: SHOPMAN_MACHINE['webhook_token'] não configurado — "
                "rejeitando. Defina MACHINE_WEBHOOK_TOKEN (inclusive em dev)."
            )
            return False
        token = request.META.get("HTTP_X_MACHINE_WEBHOOK_TOKEN", "")
        if not token:
            token = request.query_params.get("token", "")
        if not token:
            logger.warning("MachineWebhook: token ausente — rejeitando")
            return False
        if not hmac.compare_digest(token, expected):
            logger.warning("MachineWebhook: token não confere — rejeitando")
            return False
        return True


def _first(event: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = event.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return ""
