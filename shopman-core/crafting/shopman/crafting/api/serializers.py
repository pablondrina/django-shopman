"""
Craftsman API Serializers (vNext).
"""

from decimal import Decimal

from rest_framework import serializers

from shopman.crafting.models import Recipe, RecipeItem, WorkOrder, WorkOrderEvent, WorkOrderItem


class RecipeItemSerializer(serializers.ModelSerializer):
    """Serializer for RecipeItem model."""

    class Meta:
        model = RecipeItem
        fields = [
            "id",
            "input_ref",
            "quantity",
            "unit",
            "sort_order",
            "is_optional",
            "meta",
        ]


class RecipeSerializer(serializers.ModelSerializer):
    """Serializer for Recipe model."""

    items = RecipeItemSerializer(many=True, read_only=True)

    class Meta:
        model = Recipe
        fields = [
            "id",
            "code",
            "name",
            "output_ref",
            "batch_size",
            "steps",
            "is_active",
            "meta",
            "items",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class WorkOrderItemSerializer(serializers.ModelSerializer):
    """Serializer for WorkOrderItem (ledger entries)."""

    class Meta:
        model = WorkOrderItem
        fields = [
            "id",
            "kind",
            "item_ref",
            "quantity",
            "unit",
            "recorded_at",
            "recorded_by",
            "meta",
        ]


class WorkOrderEventSerializer(serializers.ModelSerializer):
    """Serializer for WorkOrderEvent (audit trail)."""

    class Meta:
        model = WorkOrderEvent
        fields = [
            "id",
            "seq",
            "kind",
            "payload",
            "actor",
            "idempotency_key",
            "created_at",
        ]


class WorkOrderSerializer(serializers.ModelSerializer):
    """Serializer for WorkOrder model."""

    recipe_code = serializers.CharField(source="recipe.code", read_only=True)
    recipe_name = serializers.CharField(source="recipe.name", read_only=True)
    loss = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True, allow_null=True,
    )
    yield_rate = serializers.DecimalField(
        max_digits=6, decimal_places=4, read_only=True, allow_null=True,
    )
    items = WorkOrderItemSerializer(many=True, read_only=True)
    events = WorkOrderEventSerializer(many=True, read_only=True)

    class Meta:
        model = WorkOrder
        fields = [
            "id",
            "code",
            "recipe",
            "recipe_code",
            "recipe_name",
            "output_ref",
            "quantity",
            "produced",
            "status",
            "rev",
            "scheduled_date",
            "started_at",
            "finished_at",
            "source_ref",
            "position_ref",
            "assigned_ref",
            "meta",
            "loss",
            "yield_rate",
            "items",
            "events",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "code",
            "recipe_code",
            "recipe_name",
            "output_ref",
            "produced",
            "status",
            "rev",
            "started_at",
            "finished_at",
            "loss",
            "yield_rate",
            "items",
            "events",
            "created_at",
            "updated_at",
        ]


class WorkOrderListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (without nested items/events)."""

    recipe_code = serializers.CharField(source="recipe.code", read_only=True)
    loss = serializers.DecimalField(
        max_digits=12, decimal_places=3, read_only=True, allow_null=True,
    )

    class Meta:
        model = WorkOrder
        fields = [
            "id",
            "code",
            "recipe_code",
            "output_ref",
            "quantity",
            "produced",
            "status",
            "rev",
            "scheduled_date",
            "started_at",
            "finished_at",
            "loss",
            "created_at",
        ]


# ── Action serializers ──


class ConsumedItemSerializer(serializers.Serializer):
    """Serializer for consumed item in close action."""

    item_ref = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3, min_value=0)
    unit = serializers.CharField(required=False, default="")
    meta = serializers.DictField(required=False, default=dict)



class CloseSerializer(serializers.Serializer):
    """Serializer for close action."""

    produced = serializers.DecimalField(
        max_digits=12, decimal_places=3,
        help_text="Quantity produced (Decimal or list of co-products)",
    )
    consumed = ConsumedItemSerializer(
        many=True, required=False, allow_null=True,
        help_text="Explicit consumption [{item_ref, quantity, unit, meta?}]",
    )
    wasted = serializers.DecimalField(
        max_digits=12, decimal_places=3, required=False, allow_null=True,
        help_text="Waste quantity (Decimal) or omit for auto-calc",
    )
    expected_rev = serializers.IntegerField(
        required=False, allow_null=True,
        help_text="Expected revision for optimistic locking",
    )
    idempotency_key = serializers.CharField(
        required=False, allow_null=True, allow_blank=True,
        help_text="Idempotency key to prevent duplicate closes",
    )
    actor = serializers.CharField(
        required=False, allow_blank=True, default="",
    )


class AdjustSerializer(serializers.Serializer):
    """Serializer for adjust action."""

    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3,
        help_text="New target quantity",
    )
    reason = serializers.CharField(
        required=False, allow_blank=True, default="",
    )
    expected_rev = serializers.IntegerField(
        required=False, allow_null=True,
    )
    actor = serializers.CharField(
        required=False, allow_blank=True, default="",
    )


class VoidSerializer(serializers.Serializer):
    """Serializer for void action."""

    reason = serializers.CharField(
        help_text="Reason for voiding",
    )
    expected_rev = serializers.IntegerField(
        required=False, allow_null=True,
    )
    actor = serializers.CharField(
        required=False, allow_blank=True, default="",
    )


# ── Plan serializer ──


class PlanSerializer(serializers.Serializer):
    """Serializer for plan action."""

    recipe_code = serializers.SlugField(
        help_text="Recipe code (slug)",
    )
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001"),
        help_text="Production quantity",
    )
    date = serializers.DateField(
        required=False, allow_null=True, default=None,
        help_text="Scheduled production date",
    )
    source_ref = serializers.CharField(
        required=False, allow_blank=True, default="",
    )
    position_ref = serializers.CharField(
        required=False, allow_blank=True, default="",
    )
    assigned_ref = serializers.CharField(
        required=False, allow_blank=True, default="",
    )
    actor = serializers.CharField(
        required=False, allow_blank=True, default="",
    )
    meta = serializers.DictField(
        required=False, default=dict,
    )


# ── Query serializers ──


class NeedSerializer(serializers.Serializer):
    """Serializer for BOM explosion needs."""

    item_ref = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit = serializers.CharField()
    has_recipe = serializers.BooleanField()


class SuggestionSerializer(serializers.Serializer):
    """Serializer for production suggestions."""

    recipe_code = serializers.CharField(source="recipe.code")
    recipe_name = serializers.CharField(source="recipe.name")
    output_ref = serializers.CharField(source="recipe.output_ref")
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    basis = serializers.DictField()
