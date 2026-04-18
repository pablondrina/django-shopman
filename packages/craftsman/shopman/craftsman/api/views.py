"""
Craftsman API ViewSets (vNext).

4 verbs: plan, adjust, start, finish.
3 queries: expected, needs, suggest.
All mutations go through craft service.
"""

from datetime import date as date_type

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from shopman.craftsman.exceptions import CraftError, StaleRevision
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.craftsman.service import craft

from .serializers import (
    AdjustSerializer,
    CraftQueueItemSerializer,
    CraftSummarySerializer,
    FinishSerializer,
    NeedSerializer,
    PlanSerializer,
    RecipeSerializer,
    StartSerializer,
    SuggestionSerializer,
    VoidSerializer,
    WorkOrderListSerializer,
    WorkOrderSerializer,
)


class CraftsmanPagination(LimitOffsetPagination):
    """Default pagination for Craftsman API."""

    default_limit = 50
    max_limit = 200


class RecipeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for Recipe (read-only).

    list: List all active recipes
    retrieve: Get a specific recipe
    """

    permission_classes = [IsAuthenticated]
    pagination_class = CraftsmanPagination
    queryset = Recipe.objects.filter(is_active=True).prefetch_related("items")
    serializer_class = RecipeSerializer
    lookup_field = "ref"


class WorkOrderViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    """
    ViewSet for WorkOrder (read-only + action verbs).

    list: List work orders (lightweight)
    retrieve: Get a specific work order (with items and events)
    plan: Create a new work order via craft.plan()
    finish: Finish a work order with final production results
    adjust: Adjust target quantity
    start: Start a planned work order with the entered quantity
    void: Cancel (void) a work order

    Create/update/delete are not exposed — all mutations go through
    craft.plan(), craft.adjust(), craft.start(), craft.finish(), craft.void().
    """

    permission_classes = [IsAuthenticated]
    pagination_class = CraftsmanPagination
    queryset = WorkOrder.objects.select_related("recipe").order_by("-created_at")
    lookup_field = "ref"

    def get_serializer_class(self):
        if self.action == "list":
            return WorkOrderListSerializer
        return WorkOrderSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        target_date = self.request.query_params.get("target_date")
        status_param = self.request.query_params.get("status")
        position_ref = self.request.query_params.get("position_ref")
        operator_ref = self.request.query_params.get("operator_ref")
        output_ref = self.request.query_params.get("output_ref")

        if target_date:
            try:
                qs = qs.filter(target_date=date_type.fromisoformat(target_date))
            except ValueError:
                return qs.none()
        if status_param:
            statuses = [item.strip() for item in status_param.split(",") if item.strip()]
            qs = qs.filter(status__in=statuses)
        if position_ref:
            qs = qs.filter(position_ref=position_ref)
        if operator_ref:
            qs = qs.filter(operator_ref=operator_ref)
        if output_ref:
            qs = qs.filter(output_ref=output_ref)
        if self.action == "retrieve":
            qs = qs.prefetch_related("items", "events")
        return qs

    @action(detail=False, methods=["post"])
    def plan(self, request):
        """
        Create a new work order via craft.plan().

        POST /api/craftsman/work-orders/plan/
        {
            "recipe_ref": "croissant-v1",
            "quantity": 100,
            "date": "2026-02-27",
            "source_ref": "order:789",
            "position_ref": "station:forno-01",
            "operator_ref": "user:joao",
            "actor": "api-user",
            "meta": {}
        }
        """
        serializer = PlanSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        recipe = Recipe.objects.filter(
            ref=data["recipe_ref"], is_active=True,
        ).first()
        if not recipe:
            return Response(
                {"error": "RECIPE_NOT_FOUND", "detail": f"Recipe '{data["recipe_ref"]}' not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            wo = craft.plan(
                recipe,
                data["quantity"],
                date=data.get("date"),
                source_ref=data.get("source_ref", ""),
                position_ref=data.get("position_ref", ""),
                operator_ref=data.get("operator_ref", ""),
                actor=data.get("actor") or request.user.username,
                meta=data.get("meta", {}),
            )
            return Response(WorkOrderSerializer(wo).data, status=status.HTTP_201_CREATED)

        except CraftError as e:
            return Response(
                {"error": e.code, "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def finish(self, request, ref=None):
        """
        Finish the work order with final production results.

        POST /api/craftsman/work-orders/{ref}/finish/
        {
            "finished": 93,
            "consumed": null,
            "wasted": null,
            "expected_rev": 0,
            "idempotency_key": "finish-wo-123"
        }
        """
        wo = self.get_object()
        serializer = FinishSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = serializer.validated_data
            result = craft.finish(
                wo,
                finished=data["finished"],
                consumed=data.get("consumed"),
                wasted=data.get("wasted"),
                expected_rev=data.get("expected_rev"),
                actor=data.get("actor", request.user.username),
                idempotency_key=data.get("idempotency_key"),
            )
            return Response(WorkOrderSerializer(result).data)

        except StaleRevision as e:
            return Response(
                {"error": "STALE_REVISION", "detail": str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        except CraftError as e:
            return Response(
                {"error": e.code, "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def adjust(self, request, ref=None):
        """
        Adjust target quantity of a planned work order.

        POST /api/craftsman/work-orders/{ref}/adjust/
        {
            "quantity": 97,
            "reason": "farinha insuficiente",
            "expected_rev": 0
        }
        """
        wo = self.get_object()
        serializer = AdjustSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = serializer.validated_data
            result = craft.adjust(
                wo,
                quantity=data["quantity"],
                reason=data.get("reason"),
                expected_rev=data.get("expected_rev"),
                actor=data.get("actor", request.user.username),
            )
            return Response(WorkOrderSerializer(result).data)

        except StaleRevision as e:
            return Response(
                {"error": "STALE_REVISION", "detail": str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        except CraftError as e:
            return Response(
                {"error": e.code, "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def start(self, request, ref=None):
        """Mark the work order as started."""
        wo = self.get_object()
        serializer = StartSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = serializer.validated_data
            result = craft.start(
                wo,
                quantity=data["quantity"],
                expected_rev=data.get("expected_rev"),
                operator_ref=data.get("operator_ref"),
                position_ref=data.get("position_ref"),
                note=data.get("note"),
                actor=data.get("actor", request.user.username),
            )
            return Response(WorkOrderSerializer(result).data)
        except StaleRevision as e:
            return Response(
                {"error": "STALE_REVISION", "detail": str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        except CraftError as e:
            return Response(
                {"error": e.code, "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )

    @action(detail=True, methods=["post"])
    def void(self, request, ref=None):
        """
        Void (cancel) a work order.

        POST /api/craftsman/work-orders/{ref}/void/
        {
            "reason": "cliente cancelou",
            "expected_rev": 0
        }
        """
        wo = self.get_object()
        serializer = VoidSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            data = serializer.validated_data
            result = craft.void(
                wo,
                reason=data["reason"],
                expected_rev=data.get("expected_rev"),
                actor=data.get("actor", request.user.username),
            )
            return Response(WorkOrderSerializer(result).data)

        except StaleRevision as e:
            return Response(
                {"error": "STALE_REVISION", "detail": str(e)},
                status=status.HTTP_409_CONFLICT,
            )
        except CraftError as e:
            return Response(
                {"error": e.code, "detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )


class QueryViewSet(viewsets.ViewSet):
    """
    ViewSet for Craftsman read-only queries.

    expected: Sum of active WorkOrder quantities for a product on a date.
    needs: BOM explosion for a date (material needs).
    suggest: Production suggestions based on demand history.
    """

    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def expected(self, request):
        """
        Sum of active WorkOrder quantities for output_ref on date.

        GET /api/craftsman/queries/expected/?output_ref=croissant&date=2026-02-27
        """
        output_ref = request.query_params.get("output_ref")
        date_str = request.query_params.get("date")

        if not output_ref or not date_str:
            return Response(
                {"error": "MISSING_PARAMS", "detail": "output_ref and date are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"error": "INVALID_DATE", "detail": f"Invalid date format: {date_str}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        total = craft.expected(output_ref, d)
        return Response({
            "output_ref": output_ref,
            "date": date_str,
            "total": str(total),
        })

    @action(detail=False, methods=["get"])
    def needs(self, request):
        """
        BOM explosion for a date — aggregated material needs.

        GET /api/craftsman/queries/needs/?date=2026-02-27&expand=true
        """
        date_str = request.query_params.get("date")
        expand = request.query_params.get("expand", "false").lower() == "true"

        if not date_str:
            return Response(
                {"error": "MISSING_PARAMS", "detail": "date is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"error": "INVALID_DATE", "detail": f"Invalid date format: {date_str}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        result = craft.needs(d, expand=expand)
        return Response(NeedSerializer(result, many=True).data)

    @action(detail=False, methods=["get"])
    def suggest(self, request):
        """
        Production suggestions based on demand history.

        GET /api/craftsman/queries/suggest/?date=2026-02-27&output_refs=croissant,baguette
        """
        date_str = request.query_params.get("date")

        if not date_str:
            return Response(
                {"error": "MISSING_PARAMS", "detail": "date is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            d = date_type.fromisoformat(date_str)
        except ValueError:
            return Response(
                {"error": "INVALID_DATE", "detail": f"Invalid date format: {date_str}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        output_refs_param = request.query_params.get("output_refs")
        output_refs = [r.strip() for r in output_refs_param.split(",")] if output_refs_param else None
        season_months_param = request.query_params.get("season_months")
        season_months = None
        if season_months_param:
            try:
                season_months = [
                    int(month.strip())
                    for month in season_months_param.split(",")
                    if month.strip()
                ]
            except ValueError:
                return Response(
                    {"error": "INVALID_SEASON_MONTHS", "detail": "season_months must be comma-separated integers."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        high_demand_multiplier_param = request.query_params.get("high_demand_multiplier")
        high_demand_multiplier = None
        if high_demand_multiplier_param:
            try:
                from decimal import Decimal

                high_demand_multiplier = Decimal(high_demand_multiplier_param)
            except Exception:
                return Response(
                    {"error": "INVALID_MULTIPLIER", "detail": "high_demand_multiplier must be a valid decimal."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        result = craft.suggest(
            d,
            output_refs=output_refs,
            season_months=season_months,
            high_demand_multiplier=high_demand_multiplier,
        )
        return Response(SuggestionSerializer(result, many=True).data)

    @action(detail=False, methods=["get"])
    def queue(self, request):
        """
        Operational queue for the floor.

        GET /api/craftsman/queries/queue/?date=2026-02-27&position_ref=forno&operator_ref=user:joao
        """
        date_str = request.query_params.get("date")
        position_ref = request.query_params.get("position_ref") or None
        operator_ref = request.query_params.get("operator_ref") or None
        statuses_param = request.query_params.get("statuses")

        d = None
        if date_str:
            try:
                d = date_type.fromisoformat(date_str)
            except ValueError:
                return Response(
                    {"error": "INVALID_DATE", "detail": f"Invalid date format: {date_str}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        statuses = [s.strip() for s in statuses_param.split(",")] if statuses_param else None
        result = craft.queue(
            date=d,
            position_ref=position_ref,
            operator_ref=operator_ref,
            statuses=statuses,
        )
        return Response(CraftQueueItemSerializer(result, many=True).data)

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """
        Operational summary for the floor.

        GET /api/craftsman/queries/summary/?date=2026-02-27&position_ref=forno&operator_ref=user:joao
        """
        date_str = request.query_params.get("date")
        position_ref = request.query_params.get("position_ref") or None
        operator_ref = request.query_params.get("operator_ref") or None

        d = None
        if date_str:
            try:
                d = date_type.fromisoformat(date_str)
            except ValueError:
                return Response(
                    {"error": "INVALID_DATE", "detail": f"Invalid date format: {date_str}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        result = craft.summary(
            date=d,
            position_ref=position_ref,
            operator_ref=operator_ref,
        )
        return Response(CraftSummarySerializer(result).data)
