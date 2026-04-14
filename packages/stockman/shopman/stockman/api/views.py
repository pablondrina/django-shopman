from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, mixins
from shopman.stockman.exceptions import StockError
from shopman.stockman.models import Hold, Move, Position, Quant
from shopman.stockman.services.alerts import check_alerts
from shopman.stockman.services.availability import (
    availability_for_sku,
    availability_for_skus,
    availability_scope_for_channel,
    promise_decision_for_sku,
    sku_exists,
)
from shopman.stockman.services.movements import StockMovements
from shopman.stockman.services.queries import StockQueries

from .serializers import (
    AvailabilitySerializer,
    BelowMinimumAlertSerializer,
    BulkAvailabilitySerializer,
    HoldSerializer,
    IssueSerializer,
    MoveResponseSerializer,
    MoveSerializer,
    PositionSerializer,
    PromiseDecisionSerializer,
    QuantSerializer,
    ReceiveSerializer,
)


class AvailabilityView(APIView):
    """GET availability for a single SKU."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        sku = request.query_params.get("sku")
        if not sku:
            return Response(
                {"detail": "sku query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not sku_exists(sku):
            return Response(
                {"detail": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        position = None
        position_ref = request.query_params.get("position_ref")
        if position_ref:
            position = Position.objects.filter(ref=position_ref).first()

        channel_ref = request.query_params.get("channel_ref")
        scope = availability_scope_for_channel(channel_ref)
        allowed_positions = None if position else scope["allowed_positions"]

        data = availability_for_sku(
            sku,
            position=position,
            safety_margin=scope["safety_margin"],
            allowed_positions=allowed_positions,
        )
        serializer = AvailabilitySerializer(data)
        return Response(serializer.data)


class BulkAvailabilityView(APIView):
    """GET bulk availability for multiple SKUs."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        skus_param = request.query_params.get("skus", "")
        if not skus_param:
            return Response(
                {"detail": "skus query parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        skus = [s.strip() for s in skus_param.split(",") if s.strip()]
        channel_ref = request.query_params.get("channel_ref")
        scope = availability_scope_for_channel(channel_ref)

        avail_map = availability_for_skus(
            skus,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
        )

        zero = Decimal("0")
        zero_breakdown = {"ready": zero, "in_production": zero, "d1": zero}
        results = []

        for sku in skus:
            data = avail_map.get(sku)
            if data is None:
                results.append({
                    "sku": sku,
                    "total_available": zero,
                    "total_promisable": zero,
                    "total_reserved": zero,
                    "breakdown": zero_breakdown,
                    "is_planned": False,
                    "is_paused": False,
                })
            else:
                results.append({
                    "sku": data["sku"],
                    "total_available": data["total_available"],
                    "total_promisable": data["total_promisable"],
                    "total_reserved": data["total_reserved"],
                    "breakdown": data["breakdown"],
                    "is_planned": data["is_planned"],
                    "is_paused": data["is_paused"],
                })

        serializer = BulkAvailabilitySerializer(results, many=True)
        return Response(serializer.data)


class PromiseView(APIView):
    """GET explicit promise decision for one SKU/quantity in scope."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        sku = request.query_params.get("sku")
        qty = request.query_params.get("qty")
        if not sku or qty is None:
            return Response(
                {"detail": "sku and qty query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not sku_exists(sku):
            return Response(
                {"detail": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            requested_qty = Decimal(qty)
        except Exception:
            return Response(
                {"detail": "qty must be a valid decimal."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_date_param = request.query_params.get("target_date")
        target_date = parse_date(target_date_param) if target_date_param else None
        if target_date_param and target_date is None:
            return Response(
                {"detail": "target_date must be in YYYY-MM-DD format."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        channel_ref = request.query_params.get("channel_ref")
        scope = availability_scope_for_channel(channel_ref)

        decision = promise_decision_for_sku(
            sku,
            requested_qty,
            target_date=target_date,
            safety_margin=scope["safety_margin"],
            allowed_positions=scope["allowed_positions"],
        )
        serializer = PromiseDecisionSerializer(decision)
        return Response(serializer.data)


class PositionViewSet(mixins.ListModelMixin, GenericViewSet):
    """List positions."""

    permission_classes = [IsAuthenticated]
    serializer_class = PositionSerializer
    lookup_field = "ref"

    def get_queryset(self):
        return Position.objects.all()

    def get_serializer(self, *args, **kwargs):
        # PositionSerializer is a plain Serializer, pass many=True for list
        if self.action == "list":
            kwargs["many"] = True
        return self.serializer_class(*args, **kwargs)


class PositionQuantsView(APIView):
    """GET quants at a specific position."""

    permission_classes = [IsAuthenticated]

    def get(self, request, ref):
        position = Position.objects.filter(ref=ref).first()
        if not position:
            return Response(
                {"detail": "Position not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        quants = Quant.objects.filter(position=position).filter(
            _quantity__gt=0
        ).select_related("position")

        min_qty = request.query_params.get("min_qty")
        if min_qty:
            quants = quants.filter(_quantity__gte=Decimal(min_qty))

        serializer = QuantSerializer(quants, many=True)
        return Response(serializer.data)


class BelowMinimumAlertView(APIView):
    """GET triggered stock alerts (below minimum)."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        position_ref = request.query_params.get("position_ref")

        triggered = check_alerts()

        results = []
        for alert, current_available in triggered:
            pos_ref = alert.position.ref if alert.position else ""

            if position_ref and pos_ref != position_ref:
                continue

            results.append({
                "sku": alert.sku,
                "position_ref": pos_ref,
                "current_qty": current_available,
                "minimum_qty": alert.min_quantity,
                "deficit": alert.min_quantity - current_available,
            })

        serializer = BelowMinimumAlertSerializer(results, many=True)
        return Response(serializer.data)


class ReceiveView(APIView):
    """POST receive stock."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ReceiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not sku_exists(data["sku"]):
            return Response(
                {"detail": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        position = Position.objects.filter(ref=data["position_ref"]).first()
        if not position:
            return Response(
                {"detail": "Position not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        reason = data.get("notes") or "Recebimento"

        try:
            quant = StockMovements.receive(
                quantity=data["qty"],
                sku=data["sku"],
                position=position,
                user=request.user,
                reason=reason,
            )
        except StockError as e:
            return Response(e.as_dict(), status=status.HTTP_400_BAD_REQUEST)

        last_move = quant.moves.order_by("-timestamp").first()

        resp = MoveResponseSerializer({
            "move_id": last_move.pk,
            "sku": data["sku"],
            "qty": data["qty"],
            "position_ref": data["position_ref"],
            "new_balance": quant._quantity,
            "created_at": last_move.timestamp,
        })
        return Response(resp.data, status=status.HTTP_201_CREATED)


class IssueView(APIView):
    """POST issue stock."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = IssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not sku_exists(data["sku"]):
            return Response(
                {"detail": "Product not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        position = Position.objects.filter(ref=data["position_ref"]).first()
        if not position:
            return Response(
                {"detail": "Position not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        quant = StockQueries.get_quant(data["sku"], position=position)
        if not quant:
            return Response(
                {"detail": "No stock found at this position."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        reason = data.get("notes") or "Saída"

        try:
            move = StockMovements.issue(
                quantity=data["qty"],
                quant=quant,
                user=request.user,
                reason=reason,
            )
        except StockError as e:
            return Response(e.as_dict(), status=status.HTTP_400_BAD_REQUEST)

        quant.refresh_from_db()

        resp = MoveResponseSerializer({
            "move_id": move.pk,
            "sku": data["sku"],
            "qty": data["qty"],
            "position_ref": data["position_ref"],
            "new_balance": quant._quantity,
            "created_at": move.timestamp,
        })
        return Response(resp.data, status=status.HTTP_201_CREATED)


class MoveListView(APIView):
    """GET paginated move history."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Move.objects.select_related("quant__position", "user").order_by("-timestamp")

        sku = request.query_params.get("sku")
        if sku:
            qs = qs.filter(quant__sku=sku)

        position_ref = request.query_params.get("position_ref")
        if position_ref:
            qs = qs.filter(quant__position__ref=position_ref)

        move_type = request.query_params.get("type")
        if move_type == "receive":
            qs = qs.filter(delta__gt=0)
        elif move_type == "issue":
            qs = qs.filter(delta__lt=0)

        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(timestamp__date__gte=date_from)

        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(timestamp__date__lte=date_to)

        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = MoveSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class HoldListView(APIView):
    """GET paginated holds."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = Hold.objects.select_related("quant__position").order_by("-created_at")

        sku = request.query_params.get("sku")
        if sku:
            qs = qs.filter(sku=sku)

        is_active = request.query_params.get("is_active")
        if is_active and is_active.lower() == "true":
            qs = qs.active()
        elif is_active and is_active.lower() == "false":
            now = timezone.now()
            qs = qs.exclude(
                Q(status__in=["pending", "confirmed"])
                & (Q(expires_at__isnull=True) | Q(expires_at__gte=now))
            )

        from rest_framework.pagination import PageNumberPagination

        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(qs, request)
        serializer = HoldSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
