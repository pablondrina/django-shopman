"""Backstage KDS API — JSON endpoints for the Kitchen Display System.

GET  /api/v1/backstage/kds/                       → list of KDS instances
GET  /api/v1/backstage/kds/<ref>/                 → KDS board projection
POST /api/v1/backstage/kds/tickets/<pk>/items/    → toggle item checked
POST /api/v1/backstage/kds/tickets/<pk>/done/     → mark ticket done
POST /api/v1/backstage/kds/expedition/<pk>/action/ → dispatch/complete
GET  /api/v1/backstage/kds/cliente/               → customer pickup board
"""

from __future__ import annotations

import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.backstage.projections.kds import (
    build_kds_board,
    build_kds_customer_status,
    build_kds_index,
    build_kds_ticket,
)
from shopman.backstage.services import kds as kds_service
from shopman.backstage.services.exceptions import KDSError

from .permissions import HasBackstagePermission, IsBackstageOperator
from .projections import projection_data

logger = logging.getLogger(__name__)


def _actor(request) -> str:
    user = getattr(request, "user", None)
    return getattr(user, "username", None) or "operator"


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="List KDS instances",
        responses={200: OpenApiResponse(description="List of KDS instance summaries.")},
    ),
)
class KDSIndexView(APIView):
    permission_classes = [IsBackstageOperator]
    required_permission = "backstage.operate_kds"

    def get(self, request):
        instances = build_kds_index()
        return Response({"instances": projection_data(instances)})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="KDS board for a station",
        responses={200: OpenApiResponse(description="KDS board projection.")},
    ),
)
class KDSBoardView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def get(self, request, ref: str):
        board = build_kds_board(ref)
        return Response({"board": projection_data(board)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Toggle KDS ticket item checked state",
        responses={200: OpenApiResponse(description="Updated ticket projection.")},
    ),
)
class KDSTicketItemView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ticket_pk: int):
        try:
            index = int(request.data.get("index", -1))
        except (TypeError, ValueError):
            return Response({"detail": "Index inválido."}, status=status.HTTP_400_BAD_REQUEST)
        checked = bool(request.data.get("checked", False))
        if index < 0:
            return Response({"detail": "Index inválido."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            kds_service.set_ticket_item_checked(
                ticket_pk=ticket_pk,
                index=index,
                checked=checked,
                actor=_actor(request),
            )
        except KDSError as exc:
            logger.debug("kds_ticket_item_update_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao atualizar item."}, status=status.HTTP_400_BAD_REQUEST)
        ticket = build_kds_ticket(ticket_pk)
        return Response({"ticket": projection_data(ticket)})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Mark KDS ticket as done",
        responses={200: OpenApiResponse(description="Ticket completion result.")},
    ),
)
class KDSTicketDoneView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ticket_pk: int):
        try:
            kds_service.mark_ticket_done(ticket_pk=ticket_pk, actor=_actor(request))
        except KDSError as exc:
            logger.debug("kds_ticket_done_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao marcar como pronto."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "ticket_pk": ticket_pk})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Recall (reopen) a done KDS ticket",
        responses={200: OpenApiResponse(description="Ticket reopened.")},
    ),
)
class KDSTicketRecallView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ticket_pk: int):
        try:
            kds_service.recall_ticket(ticket_pk=ticket_pk, actor=_actor(request))
        except KDSError as exc:
            logger.debug("kds_ticket_recall_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao reabrir."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "ticket_pk": ticket_pk})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Acknowledge a cancelled KDS ticket (dismiss from board)",
        responses={200: OpenApiResponse(description="Ticket acknowledged.")},
    ),
)
class KDSTicketAcknowledgeView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, ticket_pk: int):
        try:
            kds_service.acknowledge_ticket(ticket_pk=ticket_pk, actor=_actor(request))
        except KDSError as exc:
            logger.debug("kds_ticket_ack_failed ticket_pk=%s", ticket_pk, exc_info=True)
            return Response({"detail": str(exc) or "Falha ao dar baixa."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "ticket_pk": ticket_pk})


@extend_schema_view(
    post=extend_schema(
        tags=["backstage"],
        summary="Expedition action (dispatch/complete)",
        responses={200: OpenApiResponse(description="Action result.")},
    ),
)
class KDSExpeditionActionView(APIView):
    permission_classes = [HasBackstagePermission]
    required_permission = "backstage.operate_kds"

    def post(self, request, order_pk: int):
        action = (request.data.get("action") or "").strip()
        if action not in {"dispatch", "complete"}:
            return Response({"detail": "Ação inválida."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            kds_service.expedition_action_idempotent(
                order_id=order_pk,
                action=action,
                actor=_actor(request),
            )
        except KDSError as exc:
            logger.debug(
                "kds_expedition_action_failed order_pk=%s action=%s",
                order_pk,
                action,
                exc_info=True,
            )
            return Response({"detail": str(exc) or "Falha na ação."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True, "action": action, "order_pk": order_pk})


@extend_schema_view(
    get=extend_schema(
        tags=["backstage"],
        summary="Customer pickup board (public)",
        responses={200: OpenApiResponse(description="Customer status projection.")},
    ),
)
class KDSCustomerStatusView(APIView):
    """Public read-only endpoint for the pickup display."""

    permission_classes = []

    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 24))
        except (TypeError, ValueError):
            return Response({"detail": "Parâmetro limit inválido."}, status=status.HTTP_400_BAD_REQUEST)
        limit = max(1, min(limit, 100))
        status_proj = build_kds_customer_status(limit=limit)
        return Response({"status": projection_data(status_proj)})
