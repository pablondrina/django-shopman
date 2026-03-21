"""
Manychat Webhook View — Recebe requests inbound do Manychat.

Processa ações do agente Nice e retorna JSON no formato que o Manychat
espera para popular custom fields no subscriber.
"""

from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.ordering.exceptions import CommitError, SessionError, ValidationError
from shopman.ordering.ids import generate_idempotency_key, generate_session_key
from shopman.ordering.models import Channel, Order, Session
from shopman.ordering.services import CommitService, ModifyService

from .conf import get_webhook_setting
from .serializers import (
    AddItemSerializer,
    CheckStatusSerializer,
    CommitOrderSerializer,
    ManychatInboundSerializer,
    NewOrderSerializer,
)

logger = logging.getLogger(__name__)


class ManychatWebhookView(APIView):
    """
    Webhook endpoint para receber requests do Manychat.

    Autenticação via token no header (configurável).
    Aceita POST com payload JSON contendo action + subscriber_id + data.

    Resposta no formato Manychat-friendly:
    {
        "version": "v2",
        "content": {"messages": [{"type": "text", "text": "..."}]},
        "set_field_values": [{"field_name": "...", "field_value": "..."}]
    }
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        # 1. Validate auth token
        if not self._check_auth(request):
            return Response(
                {"error": "Invalid or missing auth token"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. Parse and validate inbound payload
        serializer = ManychatInboundSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid payload", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        action = data["action"]
        subscriber_id = data["subscriber_id"]
        action_data = data.get("data", {})

        # Merge custom_fields into action_data for convenience
        custom_fields = data.get("custom_fields", {})
        if custom_fields:
            action_data.setdefault("customer_phone", custom_fields.get("phone", ""))
            action_data.setdefault("customer_name", custom_fields.get("name", ""))

        logger.info(
            "Webhook received: action=%s subscriber=%s",
            action, subscriber_id,
        )

        # 3. Dispatch to action handler
        handler = self._get_handler(action)
        if handler is None:
            return Response(
                {"error": f"Unknown action: {action}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            result = handler(subscriber_id=subscriber_id, data=action_data)
        except Exception:
            logger.exception("Webhook action %s failed", action)
            return Response(
                {"error": "Internal error processing action"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result, status=status.HTTP_200_OK)

    def _check_auth(self, request: Request) -> bool:
        """Validate auth token from header or query param."""
        expected_token = get_webhook_setting("AUTH_TOKEN")
        if not expected_token:
            # No token configured = auth disabled (dev mode)
            return True

        header_name = get_webhook_setting("AUTH_HEADER")
        token = request.META.get(f"HTTP_{header_name.upper().replace('-', '_')}", "")
        if not token:
            token = request.query_params.get("token", "")

        return token == expected_token

    def _get_handler(self, action: str):
        """Return handler method for given action."""
        handlers = {
            "new_order": self._handle_new_order,
            "add_item": self._handle_add_item,
            "commit_order": self._handle_commit_order,
            "check_status": self._handle_check_status,
            "list_menu": self._handle_list_menu,
        }
        return handlers.get(action)

    # ── Action Handlers ──────────────────────────────────────────

    def _handle_new_order(self, *, subscriber_id: str, data: dict) -> dict:
        """
        Cria nova Session e opcionalmente adiciona items.

        Returns Manychat-friendly response com session_key.
        """
        serializer = NewOrderSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        channel_ref = get_webhook_setting("DEFAULT_CHANNEL")
        channel = Channel.objects.get(ref=channel_ref, is_active=True)

        # Get-or-open: if subscriber already has open session, reuse
        existing = Session.objects.filter(
            channel=channel,
            handle_type="subscriber",
            handle_ref=subscriber_id,
            state="open",
        ).order_by("-updated_at").first()

        if existing:
            session = existing
        else:
            session = Session.objects.create(
                session_key=generate_session_key(),
                channel=channel,
                handle_type="subscriber",
                handle_ref=subscriber_id,
                state="open",
                pricing_policy=channel.pricing_policy,
                edit_policy=channel.edit_policy,
                rev=0,
                items=[],
                data={"checks": {}, "issues": []},
            )

        # Set customer data if provided
        ops = []
        customer_phone = validated.get("customer_phone")
        customer_name = validated.get("customer_name")
        if customer_phone:
            ops.append({"op": "set_data", "path": "customer.phone", "value": customer_phone})
        if customer_name:
            ops.append({"op": "set_data", "path": "customer.name", "value": customer_name})

        # Add items if provided
        for item in validated.get("items", []):
            op = {"op": "add_line", "sku": item["sku"], "qty": item["qty"]}
            if "unit_price_q" in item:
                op["unit_price_q"] = item["unit_price_q"]
            ops.append(op)

        if ops:
            try:
                session = ModifyService.modify_session(
                    session_key=session.session_key,
                    channel_ref=channel.ref,
                    ops=ops,
                    ctx={"actor": f"webhook:{subscriber_id}"},
                )
            except (SessionError, ValidationError) as e:
                return _manychat_response(
                    text=f"Erro ao criar pedido: {e.message}",
                    fields={"last_error": e.code},
                )

        return _manychat_response(
            text="Pedido iniciado! Pode adicionar mais itens.",
            fields={
                "session_key": session.session_key,
                "items_count": str(len(session.items)),
            },
        )

    def _handle_add_item(self, *, subscriber_id: str, data: dict) -> dict:
        """Adiciona item a Session existente."""
        serializer = AddItemSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        channel_ref = get_webhook_setting("DEFAULT_CHANNEL")

        op = {
            "op": "add_line",
            "sku": validated["sku"],
            "qty": validated["qty"],
        }
        if "unit_price_q" in validated:
            op["unit_price_q"] = validated["unit_price_q"]

        try:
            session = ModifyService.modify_session(
                session_key=validated["session_key"],
                channel_ref=channel_ref,
                ops=[op],
                ctx={"actor": f"webhook:{subscriber_id}"},
            )
        except (SessionError, ValidationError) as e:
            return _manychat_response(
                text=f"Erro ao adicionar item: {e.message}",
                fields={"last_error": e.code},
            )

        return _manychat_response(
            text=f"Item adicionado! Total de itens: {len(session.items)}.",
            fields={
                "session_key": session.session_key,
                "items_count": str(len(session.items)),
            },
        )

    def _handle_commit_order(self, *, subscriber_id: str, data: dict) -> dict:
        """Fecha Session e cria Order."""
        serializer = CommitOrderSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        channel_ref = get_webhook_setting("DEFAULT_CHANNEL")

        try:
            result = CommitService.commit(
                session_key=validated["session_key"],
                channel_ref=channel_ref,
                idempotency_key=generate_idempotency_key(),
                ctx={"actor": f"webhook:{subscriber_id}"},
            )
        except (CommitError, SessionError) as e:
            return _manychat_response(
                text=f"Erro ao fechar pedido: {e.message}",
                fields={"last_error": e.code},
            )

        return _manychat_response(
            text=f"Pedido confirmado! Referência: {result['order_ref']}",
            fields={
                "order_ref": result["order_ref"],
                "order_status": "new",
            },
        )

    def _handle_check_status(self, *, subscriber_id: str, data: dict) -> dict:
        """Consulta status de Order por ref."""
        serializer = CheckStatusSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        try:
            order = Order.objects.get(ref=validated["order_ref"])
        except Order.DoesNotExist:
            return _manychat_response(
                text=f"Pedido {validated['order_ref']} não encontrado.",
                fields={"last_error": "order_not_found"},
            )

        status_display = order.get_status_display() if hasattr(order, "get_status_display") else order.status

        return _manychat_response(
            text=f"Pedido {order.ref}: {status_display}. Total: R$ {order.total_q / 100:.2f}",
            fields={
                "order_ref": order.ref,
                "order_status": order.status,
                "order_total": str(order.total_q),
            },
        )

    def _handle_list_menu(self, *, subscriber_id: str, data: dict) -> dict:
        """
        Lista produtos publicados via CatalogBackend (Protocol).

        Fallback: retorna mensagem genérica se CatalogBackend não configurado.
        """
        from shopman.ordering import registry

        catalog_backend = getattr(registry, "get_backend", lambda _: None)("catalog")
        if catalog_backend is None:
            return _manychat_response(
                text="Cardápio indisponível no momento. Por favor, consulte nosso atendente.",
                fields={},
            )

        try:
            products = catalog_backend.list_available()
        except Exception:
            logger.exception("Webhook list_menu: catalog backend error")
            return _manychat_response(
                text="Erro ao consultar cardápio. Tente novamente.",
                fields={"last_error": "catalog_error"},
            )

        if not products:
            return _manychat_response(
                text="Nenhum produto disponível no momento.",
                fields={},
            )

        lines = []
        for p in products[:20]:  # Limita para não estourar mensagem
            name = p.get("name", p.get("sku", "???"))
            price_q = p.get("price_q", 0)
            lines.append(f"• {name} — R$ {price_q / 100:.2f}")

        text = "Cardápio disponível:\n" + "\n".join(lines)
        return _manychat_response(text=text, fields={"menu_count": str(len(products))})


def _manychat_response(*, text: str, fields: dict) -> dict:
    """
    Build Manychat-friendly response.

    Formato que o Manychat aceita para:
    1. Enviar mensagem de resposta
    2. Popular custom fields no subscriber
    """
    response = {
        "version": "v2",
        "content": {
            "messages": [
                {"type": "text", "text": text},
            ],
        },
    }

    if fields:
        response["set_field_values"] = [
            {"field_name": k, "field_value": v}
            for k, v in fields.items()
        ]

    return response
