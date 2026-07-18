"""Backstage API — notificações pessoais do operador.

GET  /api/v1/backstage/notifications/             → não lidas do usuário atual
POST /api/v1/backstage/notifications/<pk>/read/   → marcar como lida
POST /api/v1/backstage/notifications/<pk>/action/ → executar a ação acionável

Diferente de ``alerts.py``, que é da LOJA (qualquer operador vê o mesmo painel),
isto é da PESSOA: o gestor recebe o pedido de aprovação onde estiver. Por isso
todo queryset é filtrado por ``request.user`` — nem staff lê a caixa alheia.
"""

from __future__ import annotations

import logging

from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema, extend_schema_view
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.shop.models import UserNotification

from .permissions import IsBackstageOperator

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 20
_MAX_LIMIT = 100

#: Ações que uma notificação acionável pode disparar.
ACTION_APPROVE = "approve"
ACTION_DISCARD = "discard"


def _notification_dict(notification: UserNotification) -> dict:
    return {
        "pk": notification.pk,
        "category": notification.category,
        "title": notification.title,
        "message": notification.message,
        "action_url": notification.action_url,
        "action_data": notification.action_data or {},
        "is_actionable": notification.is_actionable,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat(),
        "created_at_display": timezone.localtime(notification.created_at).strftime(
            "%d/%m às %H:%M"
        ),
    }


def _own(request):
    """Só a caixa de quem está pedindo. Nunca aceitar user_id do cliente."""
    return UserNotification.objects.filter(user=request.user)


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Personal notifications for the current user",
        parameters=[
            OpenApiParameter("limit", int, description="Máximo de itens (default 20)."),
            OpenApiParameter("all", bool, description="Inclui as já lidas."),
        ],
        responses={200: OpenApiResponse(description="Notifications, newest first.")},
    ),
)
class NotificationListView(APIView):
    permission_classes = [IsBackstageOperator]

    def get(self, request):
        queryset = _own(request)
        if not _flag(request, "all"):
            queryset = queryset.filter(is_read=False)

        limit = _limit(request)
        notifications = list(queryset[:limit])
        return Response({
            "notifications": [_notification_dict(n) for n in notifications],
            "unread_count": _own(request).filter(is_read=False).count(),
            "actionable_count": _own(request)
            .filter(is_read=False, is_actionable=True)
            .count(),
        })


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Mark a notification as read",
        responses={200: OpenApiResponse(description="Notification marked as read.")},
    ),
)
class NotificationReadView(APIView):
    permission_classes = [IsBackstageOperator]

    def post(self, request, pk: int):
        notification = _own(request).filter(pk=pk).first()
        if notification is None:
            return Response({"detail": "Notificação não encontrada."}, status=404)
        notification.mark_read()
        return Response({"ok": True, "pk": pk, "unread_count": _unread(request)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Execute a notification's action (e.g. approve a broadcast post)",
        responses={200: OpenApiResponse(description="Action executed.")},
    ),
)
class NotificationActionView(APIView):
    """Executar a decisão pedida pela notificação, sem sair de onde se está.

    Hoje só broadcast (aprovar/descartar um post). A ação marca a notificação
    como lida no sucesso — a decisão já foi tomada, o card sai da caixa.
    """

    permission_classes = [IsBackstageOperator]

    def post(self, request, pk: int):
        notification = _own(request).filter(pk=pk).first()
        if notification is None:
            return Response({"detail": "Notificação não encontrada."}, status=404)
        if not notification.is_actionable:
            return Response(
                {"detail": "Esta notificação não pede nenhuma ação."}, status=400
            )

        action = str(request.data.get("action") or ACTION_APPROVE).strip()
        if action not in (ACTION_APPROVE, ACTION_DISCARD):
            return Response(
                {"detail": "Ação desconhecida.", "field": "action"}, status=400
            )

        post_id = (notification.action_data or {}).get("broadcast_post_id")
        if not post_id:
            return Response(
                {"detail": "Esta notificação não aponta para nenhum post."}, status=400
            )

        if not request.user.has_perm("shop.manage_broadcast"):
            return Response(
                {"detail": "Você não tem permissão para publicar."}, status=403
            )

        from shopman.shop.services import broadcast

        try:
            post = (
                broadcast.approve(post_id, request.user)
                if action == ACTION_APPROVE
                else broadcast.discard(post_id)
            )
        except broadcast.BroadcastError as exc:
            # Expirado ou inexistente: a notificação perdeu o sentido, então
            # some da caixa junto com o erro.
            notification.mark_read()
            return Response({"detail": str(exc)}, status=400)

        notification.mark_read()
        logger.info(
            "notification.action user=%s action=%s post=%s", request.user.pk, action, post_id
        )
        return Response({
            "ok": True,
            "action": action,
            "post_id": post.pk,
            "status": post.status,
            "unread_count": _unread(request),
        })


def _unread(request) -> int:
    return _own(request).filter(is_read=False).count()


def _limit(request) -> int:
    raw = request.query_params.get("limit")
    try:
        return max(1, min(int(raw), _MAX_LIMIT)) if raw else _DEFAULT_LIMIT
    except (TypeError, ValueError):
        return _DEFAULT_LIMIT


def _flag(request, name: str) -> bool:
    return str(request.query_params.get(name) or "").lower() in ("1", "true", "yes")
