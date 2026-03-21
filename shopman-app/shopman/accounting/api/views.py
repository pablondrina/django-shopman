"""
Shopman Accounting API — Views.
"""

from __future__ import annotations

import logging
from datetime import date

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from shopman.ordering.protocols import AccountingBackend

from .serializers import (
    AccountEntrySerializer,
    AccountsSummarySerializer,
    CashFlowSummarySerializer,
    CreateEntryResultSerializer,
    CreatePayableSerializer,
)

logger = logging.getLogger(__name__)

# Backend instance — set via set_accounting_backend()
_accounting_backend: AccountingBackend | None = None


def set_accounting_backend(backend: AccountingBackend) -> None:
    """Registra o backend contábil para uso nas views."""
    global _accounting_backend  # noqa: PLW0603
    _accounting_backend = backend


def get_accounting_backend() -> AccountingBackend | None:
    """Retorna o backend contábil registrado."""
    return _accounting_backend


class CashFlowView(APIView):
    """
    GET /api/accounting/cash-flow/
    Query params: start_date, end_date
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        backend = get_accounting_backend()
        if not backend:
            return Response(
                {"error": "Accounting backend not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        start_date_str = request.query_params.get("start_date")
        end_date_str = request.query_params.get("end_date")

        if not start_date_str or not end_date_str:
            return Response(
                {"error": "start_date and end_date are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            start = date.fromisoformat(start_date_str)
            end = date.fromisoformat(end_date_str)
        except ValueError:
            return Response(
                {"error": "Invalid date format. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        summary = backend.get_cash_flow(start_date=start, end_date=end)
        return Response(CashFlowSummarySerializer(summary).data)


class AccountsSummaryView(APIView):
    """
    GET /api/accounting/accounts/
    Query params: as_of (optional)
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        backend = get_accounting_backend()
        if not backend:
            return Response(
                {"error": "Accounting backend not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        as_of_str = request.query_params.get("as_of")
        as_of = date.fromisoformat(as_of_str) if as_of_str else None

        summary = backend.get_accounts_summary(as_of=as_of)
        return Response(AccountsSummarySerializer(summary).data)


class EntriesView(APIView):
    """
    GET /api/accounting/entries/
    Query params: start_date, end_date, type, status, category, limit, offset
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        backend = get_accounting_backend()
        if not backend:
            return Response(
                {"error": "Accounting backend not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        params = request.query_params
        start_date = (
            date.fromisoformat(params["start_date"])
            if params.get("start_date") else None
        )
        end_date = (
            date.fromisoformat(params["end_date"])
            if params.get("end_date") else None
        )

        entries = backend.list_entries(
            start_date=start_date,
            end_date=end_date,
            type=params.get("type"),
            status=params.get("status"),
            category=params.get("category"),
            reference=params.get("reference"),
            limit=int(params.get("limit", 50)),
            offset=int(params.get("offset", 0)),
        )
        return Response(AccountEntrySerializer(entries, many=True).data)


class CreatePayableView(APIView):
    """
    POST /api/accounting/payables/
    Body: {description, amount_q, due_date, category, supplier_name?, reference?}
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        backend = get_accounting_backend()
        if not backend:
            return Response(
                {"error": "Accounting backend not configured"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        serializer = CreatePayableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = backend.create_payable(
            description=data["description"],
            amount_q=data["amount_q"],
            due_date=data["due_date"],
            category=data["category"],
            supplier_name=data.get("supplier_name"),
            reference=data.get("reference"),
            notes=data.get("notes"),
        )

        result_status = (
            status.HTTP_201_CREATED if result.success
            else status.HTTP_400_BAD_REQUEST
        )
        return Response(
            CreateEntryResultSerializer(result).data,
            status=result_status,
        )
