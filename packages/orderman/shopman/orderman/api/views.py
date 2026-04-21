"""
Orderman API Views — ViewSets para a REST API.

Este módulo implementa os endpoints REST para gestão de canais, sessões,
pedidos e diretivas. Usa Django REST Framework com suporte a throttling
configurável.

Configuração de Throttling:
    Configure em settings.py:

    REST_FRAMEWORK = {
        'DEFAULT_THROTTLE_CLASSES': [
            'rest_framework.throttling.AnonRateThrottle',
            'rest_framework.throttling.UserRateThrottle'
        ],
        'DEFAULT_THROTTLE_RATES': {
            'anon': '100/hour',
            'user': '1000/hour',
            'orderman_modify': '300/minute',  # Rate limit para modificações
            'orderman_commit': '60/minute',   # Rate limit para commits
        }
    }
"""

from __future__ import annotations

import logging
from dataclasses import asdict

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.pagination import CursorPagination
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from shopman.orderman.conf import get_orderman_setting
from shopman.orderman.exceptions import CommitError, IssueResolveError, SessionError, ValidationError
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Directive, Order, Session
from shopman.orderman.services import CommitService, ModifyService, ResolveService

from .serializers import (
    DirectiveSerializer,
    OrderSerializer,
    SessionCommitSerializer,
    SessionCreateSerializer,
    SessionModifySerializer,
    SessionResolveSerializer,
    SessionSerializer,
)

logger = logging.getLogger(__name__)


# H26: Default pagination for list endpoints.
# Uses CursorPagination for stable ordering with large datasets.
class OrderCursorPagination(CursorPagination):
    """Cursor-based pagination for Orderman API endpoints."""

    page_size = 25
    ordering = "-created_at"
    page_size_query_param = "page_size"
    max_page_size = 100


def _get_actor(request) -> str:
    """Extrai username do request ou retorna 'api' como fallback."""
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "api"


class CommitRateThrottle(UserRateThrottle):
    """
    Throttle específico para operações de commit.

    Limita a taxa de commits para prevenir abuso.
    Configure via 'orderman_commit' em DEFAULT_THROTTLE_RATES.
    """

    scope = "orderman_commit"


class ModifyRateThrottle(UserRateThrottle):
    """
    Throttle específico para operações de modify.

    Limita a taxa de modificações para prevenir abuso.
    Configure via 'orderman_modify' em DEFAULT_THROTTLE_RATES.
    Default: 300/minute (5 ops/segundo por usuário).
    """

    scope = "orderman_modify"


class ChannelViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para canais de venda (shopman.Channel).

    Endpoints:
        GET /api/channels - Lista todos os canais
        GET /api/channels/{id} - Detalhes de um canal

    Canais são read-only via API. Configuração é feita via admin.
    """

    @property
    def queryset(self):
        from shopman.shop.models import Channel
        return Channel.objects.all()

    @property
    def serializer_class(self):
        from rest_framework import serializers as drf_serializers

        from shopman.shop.models import Channel

        class ChannelSerializer(drf_serializers.ModelSerializer):
            class Meta:
                model = Channel
                fields = ("id", "ref", "name", "kind", "display_order", "is_active")

        return ChannelSerializer

    permission_classes = get_orderman_setting("DEFAULT_PERMISSION_CLASSES")
    throttle_classes = [AnonRateThrottle, UserRateThrottle]


class SessionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """
    ViewSet para sessões (carrinhos/comandas).

    Endpoints:
        GET  /api/sessions - Lista sessões
        POST /api/sessions - Abre nova sessão
        GET  /api/sessions/{key}?channel_ref=X - Detalhes da sessão
        POST /api/sessions/{key}/modify - Modifica sessão (add/remove items)
        POST /api/sessions/{key}/resolve - Resolve issue
        POST /api/sessions/{key}/commit - Finaliza sessão, cria pedido

    Notas:
        - Session é única por (channel, session_key)
        - Para rotas detail, channel_ref pode ser query param ou body
        - Commit é idempotente via idempotency_key

    Throttling:
        - Operações de commit têm rate limit específico (CommitRateThrottle)
    """

    queryset = Session.objects.all()
    serializer_class = SessionSerializer
    permission_classes = get_orderman_setting("DEFAULT_PERMISSION_CLASSES")
    pagination_class = OrderCursorPagination
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    lookup_field = "session_key"
    lookup_url_kwarg = "session_key"

    def get_queryset(self):
        qs = super().get_queryset()
        channel_ref = self.request.query_params.get("channel_ref")
        if channel_ref:
            qs = qs.filter(channel_ref=channel_ref)
        return qs

    def _get_channel_ref_from_request(self) -> str | None:
        # Para GET /retrieve, `channel_ref` tende a vir em querystring.
        code = self.request.query_params.get("channel_ref")
        if code:
            return code
        # Para POST actions, pode vir no body.
        data = getattr(self.request, "data", {}) or {}
        # Quando usamos SlugRelatedField(source="channel") o payload original é channel_ref,
        # mas aqui ainda não passou pelo serializer; então lemos direto.
        return data.get("channel_ref")

    def get_object(self):
        session_key = self.kwargs.get(self.lookup_url_kwarg or self.lookup_field)
        if not session_key:
            raise NotFound("Sessão não encontrada.")

        channel_ref = self._get_channel_ref_from_request()

        qs = Session.objects.filter(session_key=session_key)
        if channel_ref:
            qs = qs.filter(channel_ref=channel_ref)

        matches = list(qs[:2])
        if not matches:
            raise NotFound("Sessão não encontrada.")
        if len(matches) > 1 and not channel_ref:
            raise DRFValidationError(
                {"channel_ref": "Obrigatório quando session_key existe em mais de um canal."}
            )
        return matches[0]

    def create(self, request, *args, **kwargs):
        s = SessionCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        channel_ref: str = s.validated_data["channel_ref"]

        handle_type = s.validated_data.get("handle_type")
        handle_ref = s.validated_data.get("handle_ref")

        # get-or-open por owner quando handle_type+handle_ref é usado.
        if handle_type and handle_ref:
            existing = (
                Session.objects.filter(
                    channel_ref=channel_ref,
                    handle_type=handle_type,
                    handle_ref=handle_ref,
                    state="open",
                )
                .order_by("-updated_at")
                .first()
            )
            if existing:
                return Response(SessionSerializer(existing).data, status=status.HTTP_200_OK)

        session_key = s.validated_data.get("session_key") or generate_session_key()

        session = Session.objects.create(
            session_key=session_key,
            channel_ref=channel_ref,
            handle_type=handle_type,
            handle_ref=handle_ref,
            state="open",
            rev=0,
            items=[],
            data={"checks": {}, "issues": []},
        )
        return Response(SessionSerializer(session).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="modify", throttle_classes=[ModifyRateThrottle])
    def modify(self, request, *args, **kwargs):
        s = SessionModifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        channel_ref: str = s.validated_data["channel_ref"]
        ops = s.validated_data["ops"]

        session_key = self.kwargs[self.lookup_url_kwarg or self.lookup_field]
        try:
            updated = ModifyService.modify_session(
                session_key=session_key,
                channel_ref=channel_ref,
                ops=ops,
                ctx={"actor": _get_actor(request)},
            )
        except (SessionError, ValidationError) as e:
            raise DRFValidationError({"code": e.code, "message": e.message, "context": e.context}) from e

        return Response(SessionSerializer(updated).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="resolve")
    def resolve(self, request, *args, **kwargs):
        s = SessionResolveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        channel_ref: str = s.validated_data["channel_ref"]
        issue_id = s.validated_data["issue_id"]
        action_id = s.validated_data["action_id"]

        session_key = self.kwargs[self.lookup_url_kwarg or self.lookup_field]
        try:
            updated = ResolveService.resolve(
                session_key=session_key,
                channel_ref=channel_ref,
                issue_id=issue_id,
                action_id=action_id,
                ctx={"actor": _get_actor(request)},
            )
        except IssueResolveError as e:
            raise DRFValidationError({"code": e.code, "message": e.message, "context": e.context}) from e
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception(
                "API resolve falhou para sessão %s (issue %s action %s)",
                session_key,
                issue_id,
                action_id,
            )
            raise DRFValidationError(
                {
                    "code": "resolver_error",
                    "message": "Falha inesperada ao resolver issue.",
                    "context": {"session_key": session_key, "issue_id": issue_id, "action_id": action_id},
                }
            ) from exc

        return Response(SessionSerializer(updated).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="commit", throttle_classes=[CommitRateThrottle])
    def commit(self, request, *args, **kwargs):
        """
        Finaliza uma sessão e cria um pedido.

        Este endpoint é idempotente quando fornecido idempotency_key.
        Se não fornecido, um será gerado automaticamente.

        Args:
            channel_ref: Código do canal
            idempotency_key: Chave para garantir idempotência (opcional)

        Returns:
            201: Pedido criado com sucesso
            200: Pedido já existia (idempotência)
            400: Erro de validação ou commit
        """
        s = SessionCommitSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        channel_ref: str = s.validated_data["channel_ref"]
        idempotency_key = s.validated_data.get("idempotency_key") or generate_idempotency_key()

        session_key = self.kwargs[self.lookup_url_kwarg or self.lookup_field]

        logger.info(
            "Commit requested",
            extra={
                "session_key": session_key,
                "channel_ref": channel_ref,
                "idempotency_key": idempotency_key,
                "actor": _get_actor(request),
            },
        )

        try:
            result = CommitService.commit(
                session_key=session_key,
                channel_ref=channel_ref,
                idempotency_key=idempotency_key,
                ctx={"actor": _get_actor(request)},
            )
        except (CommitError, SessionError) as e:
            logger.warning(
                "Commit failed",
                extra={
                    "session_key": session_key,
                    "channel_ref": channel_ref,
                    "error_code": e.code,
                    "error_message": e.message,
                },
            )
            raise DRFValidationError({"code": e.code, "message": e.message, "context": e.context}) from e

        logger.info(
            "Commit successful",
            extra={
                "session_key": session_key,
                "channel_ref": channel_ref,
                "order_ref": result.order_ref,
            },
        )

        http_status = status.HTTP_201_CREATED if result.status == "committed" else status.HTTP_200_OK
        return Response(asdict(result), status=http_status)


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para pedidos (read-only).

    Endpoints:
        GET /api/orders - Lista pedidos
        GET /api/orders/{ref} - Detalhes do pedido

    Pedidos são imutáveis após criação. Modificações de status
    são feitas via admin ou transições programáticas.
    """

    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = get_orderman_setting("DEFAULT_PERMISSION_CLASSES")
    pagination_class = OrderCursorPagination
    throttle_classes = [AnonRateThrottle, UserRateThrottle]
    lookup_field = "ref"


class DirectiveViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet para diretivas (read-only).

    Endpoints:
        GET /api/directives - Lista diretivas
        GET /api/directives/{id} - Detalhes da diretiva

    Diretivas são tarefas assíncronas criadas automaticamente.
    Processamento é feito via workers ou management commands.
    """

    queryset = Directive.objects.all()
    serializer_class = DirectiveSerializer
    permission_classes = get_orderman_setting("ADMIN_PERMISSION_CLASSES")
    pagination_class = OrderCursorPagination
    throttle_classes = [AnonRateThrottle, UserRateThrottle]
