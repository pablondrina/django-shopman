from __future__ import annotations

from rest_framework import serializers

# ── Availability ──────────────────────────────────────────────────

class PositionAvailabilitySerializer(serializers.Serializer):
    position_ref = serializers.CharField()
    position_name = serializers.CharField()
    available = serializers.DecimalField(max_digits=12, decimal_places=3)
    reserved = serializers.DecimalField(max_digits=12, decimal_places=3)


class BreakdownSerializer(serializers.Serializer):
    ready = serializers.DecimalField(max_digits=12, decimal_places=3)
    in_production = serializers.DecimalField(max_digits=12, decimal_places=3)
    d1 = serializers.DecimalField(max_digits=12, decimal_places=3)


class AvailabilitySerializer(serializers.Serializer):
    sku = serializers.CharField()
    availability_policy = serializers.CharField(required=False)
    total_available = serializers.DecimalField(max_digits=12, decimal_places=3)
    total_promisable = serializers.DecimalField(max_digits=12, decimal_places=3)
    total_reserved = serializers.DecimalField(max_digits=12, decimal_places=3)
    breakdown = BreakdownSerializer(required=False)
    is_planned = serializers.BooleanField(default=False)
    is_paused = serializers.BooleanField(default=False)
    positions = PositionAvailabilitySerializer(many=True, required=False)


class BulkAvailabilitySerializer(serializers.Serializer):
    sku = serializers.CharField()
    availability_policy = serializers.CharField(required=False)
    total_available = serializers.DecimalField(max_digits=12, decimal_places=3)
    total_promisable = serializers.DecimalField(max_digits=12, decimal_places=3)
    total_reserved = serializers.DecimalField(max_digits=12, decimal_places=3)
    breakdown = BreakdownSerializer(required=False)
    is_planned = serializers.BooleanField(default=False)
    is_paused = serializers.BooleanField(default=False)


# ── Promise ──────────────────────────────────────────────────────

class PromiseDecisionSerializer(serializers.Serializer):
    approved = serializers.BooleanField()
    sku = serializers.CharField()
    requested_qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    target_date = serializers.DateField(allow_null=True)
    availability_policy = serializers.CharField(required=False)
    reason_code = serializers.CharField(allow_null=True, required=False)
    available_qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    available = serializers.DecimalField(max_digits=12, decimal_places=3)
    expected = serializers.DecimalField(max_digits=12, decimal_places=3)
    planned = serializers.DecimalField(max_digits=12, decimal_places=3)
    is_planned = serializers.BooleanField(default=False)
    is_paused = serializers.BooleanField(default=False)


# ── Positions / Quants ────────────────────────────────────────────

class PositionSerializer(serializers.Serializer):
    ref = serializers.CharField()
    name = serializers.CharField()
    kind = serializers.CharField()
    is_saleable = serializers.BooleanField()


class QuantSerializer(serializers.Serializer):
    sku = serializers.CharField()
    position_ref = serializers.SerializerMethodField()
    quantity = serializers.DecimalField(source="_quantity", max_digits=12, decimal_places=3)
    available = serializers.DecimalField(max_digits=12, decimal_places=3)
    batch = serializers.CharField()
    target_date = serializers.DateField()
    last_move_at = serializers.SerializerMethodField()

    def get_position_ref(self, obj) -> str:
        return obj.position.ref if obj.position else ""

    def get_last_move_at(self, obj) -> str | None:
        last_move = obj.moves.order_by("-timestamp").values_list("timestamp", flat=True).first()
        if last_move:
            return last_move.isoformat()
        return None


# ── Alerts ────────────────────────────────────────────────────────

class BelowMinimumAlertSerializer(serializers.Serializer):
    sku = serializers.CharField()
    position_ref = serializers.CharField(allow_blank=True)
    current_qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    minimum_qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    deficit = serializers.DecimalField(max_digits=12, decimal_places=3)


# ── Movements (write) ────────────────────────────────────────────

class ReceiveSerializer(serializers.Serializer):
    sku = serializers.CharField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    position_ref = serializers.CharField()
    reference = serializers.CharField(max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class IssueSerializer(serializers.Serializer):
    sku = serializers.CharField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    position_ref = serializers.CharField()
    reference = serializers.CharField(max_length=100)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    batch_ref = serializers.CharField(required=False, allow_blank=True, default="")
    target_date = serializers.DateField(required=False, allow_null=True, default=None)


class MoveResponseSerializer(serializers.Serializer):
    move_id = serializers.IntegerField()
    sku = serializers.CharField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    position_ref = serializers.CharField()
    new_balance = serializers.DecimalField(max_digits=12, decimal_places=3)
    created_at = serializers.DateTimeField()


# ── History (read-only) ──────────────────────────────────────────

class MoveSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.SerializerMethodField()
    position_ref = serializers.SerializerMethodField()
    delta = serializers.DecimalField(max_digits=12, decimal_places=3)
    move_type = serializers.SerializerMethodField()
    reason = serializers.CharField()
    timestamp = serializers.DateTimeField()
    user = serializers.SerializerMethodField()

    def get_sku(self, obj) -> str:
        return obj.quant.sku

    def get_position_ref(self, obj) -> str:
        return obj.quant.position.ref if obj.quant.position else ""

    def get_move_type(self, obj) -> str:
        return "receive" if obj.delta > 0 else "issue"

    def get_user(self, obj) -> str | None:
        return obj.user.username if obj.user else None


class HoldSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    sku = serializers.CharField()
    quantity = serializers.DecimalField(max_digits=12, decimal_places=3)
    target_date = serializers.DateField()
    status = serializers.CharField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()
    expires_at = serializers.DateTimeField()
