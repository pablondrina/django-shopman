from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet, mixins

from shopman.stocking.exceptions import StockError
from shopman.stocking.models import Hold, Move, Position, Quant, StockAlert
from shopman.stocking.services.alerts import check_alerts
from shopman.stocking.services.movements import StockMovements
from shopman.stocking.services.queries import StockQueries

from .serializers import (
    AvailabilitySerializer,
    BelowMinimumAlertSerializer,
    BulkAvailabilitySerializer,
    HoldSerializer,
    MoveResponseSerializer,
    MoveSerializer,
    PositionSerializer,
    QuantSerializer,
    ReceiveSerializer,
    IssueSerializer,
)


def _sku_exists(sku: str) -> bool:
    """Check if SKU exists via offering.Product."""
    from shopman.offering.models import Product
    return Product.objects.filter(sku=sku).exists()


def _product_is_orderable(sku: str) -> bool:
    """Check if product is published AND available for sale."""
    from shopman.offering.models import Product
    return Product.objects.filter(
        sku=sku, is_published=True, is_available=True,
    ).exists()


def _availability_for_sku(
    sku: str,
    position=None,
    safety_margin: int = 0,
    *,
    allowed_positions: list[str] | None = None,
) -> dict:
    """
    Build availability dict for a SKU with breakdown.

    Breakdown categories:
    - ready: Position.is_saleable=True, batch != "D-1"
    - in_production: Position.is_saleable=False (e.g. producao)
    - d1: batch == "D-1" (yesterday's leftovers)

    total_available = ready - held - safety_margin (only saleable stock).
    is_planned = True if any quant has a future target_date.

    If product is paused (is_available=False or is_published=False),
    returns zeros for orderable/available — stock may exist but is not for sale.

    ``allowed_positions``: when not None, only quants at those position refs are
    considered (e.g. remote channels exclude ``ontem`` so D-1 leftovers there are
    invisible online). Ignored when ``position`` is set (single-position query).
    """
    from shopman.stocking.models import Batch

    zero = Decimal("0")
    zero_breakdown = {"ready": zero, "in_production": zero, "d1": zero}
    orderable = _product_is_orderable(sku)

    # If product is paused, return zeros (stock exists but not for sale)
    if not orderable:
        return {
            "sku": sku,
            "total_available": zero,
            "total_orderable": zero,
            "total_reserved": zero,
            "breakdown": zero_breakdown,
            "is_planned": False,
            "is_paused": True,
            "positions": [],
        }

    today = date.today()

    # Expired batch refs for this SKU (loose coupling via string)
    expired_refs = set(
        Batch.objects.filter(sku=sku, expiry_date__lt=today)
        .values_list("ref", flat=True)
    )

    # Check if there are planned (future) quants → is_planned flag
    is_planned = Quant.objects.filter(
        sku=sku, target_date__gt=today, _quantity__gt=0,
    ).exists()

    quants = (
        Quant.objects.filter(sku=sku)
        .filter(Q(target_date__isnull=True) | Q(target_date__lte=today))
        .filter(_quantity__gt=0)
        .select_related("position")
    )

    if position:
        quants = quants.filter(position=position)
    elif allowed_positions is not None:
        quants = quants.filter(position__ref__in=allowed_positions)

    ready = Decimal("0")
    in_production = Decimal("0")
    d1 = Decimal("0")
    held_ready = Decimal("0")
    held_production = Decimal("0")
    held_d1 = Decimal("0")
    positions_data = []

    for quant in quants:
        if quant.batch and quant.batch in expired_refs:
            continue

        qty = quant._quantity
        held = quant.held

        # Classify into breakdown buckets
        if quant.batch == "D-1":
            d1 += qty
            held_d1 += held
        elif quant.position and quant.position.kind == "process":
            # PROCESS position = production stage (forno, bancada, etc.)
            in_production += qty
            held_production += held
        elif quant.position and quant.position.is_saleable:
            ready += qty
            held_ready += held

        if quant.position:
            positions_data.append({
                "position_ref": quant.position.ref,
                "position_name": quant.position.name,
                "available": qty - held,
                "reserved": held,
                "batch": quant.batch or None,
            })

    total_held = held_ready + held_production + held_d1

    # total_available = ready stock minus holds minus safety margin
    total_available = max(ready - held_ready - safety_margin, Decimal("0"))

    # total_orderable = everything that can be reserved (ready + production, net of holds)
    total_orderable = max(
        ready + in_production - held_ready - held_production - safety_margin,
        Decimal("0"),
    )

    return {
        "sku": sku,
        "total_available": total_available,
        "total_orderable": total_orderable,
        "total_reserved": total_held,
        "breakdown": {
            "ready": ready - held_ready,
            "in_production": in_production - held_production,
            "d1": d1 - held_d1,
        },
        "is_planned": is_planned,
        "is_paused": False,
        "positions": positions_data,
    }


def _get_safety_margin(channel_ref: str | None) -> int:
    """Get safety_margin from Channel.config, default 0."""
    if not channel_ref:
        return 0
    from shopman.ordering.models import Channel
    try:
        channel = Channel.objects.get(ref=channel_ref)
        return int(channel.config.get("safety_margin", 0))
    except Channel.DoesNotExist:
        return 0


def _get_allowed_positions(channel_ref: str | None) -> list[str] | None:
    """stock.allowed_positions from Channel.config. None = todas as posições."""
    if not channel_ref:
        return None
    from shopman.ordering.models import Channel
    try:
        channel = Channel.objects.get(ref=channel_ref)
        return (channel.config or {}).get("stock", {}).get("allowed_positions")
    except Channel.DoesNotExist:
        return None


def availability_scope_for_channel(channel_ref: str | None) -> dict[str, int | list[str] | None]:
    """Único ponto para margem + posições ao calcular disponibilidade por canal.

    O catálogo (o que o canal “oferece”) vem da Listagem vinculada ao canal; estes
    parâmetros só restringem **de quais posições físicas** o estoque conta para esse
    canal (ex.: remoto sem ``ontem`` para D-1 só no balcão).
    """
    return {
        "safety_margin": _get_safety_margin(channel_ref),
        "allowed_positions": _get_allowed_positions(channel_ref),
    }


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

        if not _sku_exists(sku):
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

        data = _availability_for_sku(
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
        results = []

        zero_breakdown = {"ready": Decimal("0"), "in_production": Decimal("0"), "d1": Decimal("0")}

        for sku in skus:
            if not _sku_exists(sku):
                results.append({
                    "sku": sku,
                    "total_available": Decimal("0"),
                    "total_orderable": Decimal("0"),
                    "total_reserved": Decimal("0"),
                    "breakdown": zero_breakdown,
                    "is_planned": False,
                    "is_paused": False,
                })
                continue
            data = _availability_for_sku(
                sku,
                safety_margin=scope["safety_margin"],
                allowed_positions=scope["allowed_positions"],
            )
            results.append({
                "sku": data["sku"],
                "total_available": data["total_available"],
                "total_orderable": data["total_orderable"],
                "total_reserved": data["total_reserved"],
                "breakdown": data["breakdown"],
                "is_planned": data["is_planned"],
                "is_paused": data["is_paused"],
            })

        serializer = BulkAvailabilitySerializer(results, many=True)
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

        if not _sku_exists(data["sku"]):
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

        if not _sku_exists(data["sku"]):
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
