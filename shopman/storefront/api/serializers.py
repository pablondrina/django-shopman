from __future__ import annotations

from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers


class CartItemSerializer(serializers.Serializer):
    line_id = serializers.CharField(read_only=True)
    sku = serializers.CharField()
    qty = serializers.IntegerField(min_value=1)
    unit_price_q = serializers.IntegerField(read_only=True)
    line_total_q = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True, required=False)


class CartSerializer(serializers.Serializer):
    items = CartItemSerializer(many=True, read_only=True)
    subtotal_q = serializers.IntegerField(read_only=True)
    count = serializers.IntegerField(read_only=True)
    session_key = serializers.CharField(read_only=True, required=False)


class AddItemSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=64)
    qty = serializers.IntegerField(min_value=1, max_value=99, default=1)


class UpdateItemSerializer(serializers.Serializer):
    qty = serializers.IntegerField(min_value=1, max_value=99)


class SetSkuQtySerializer(serializers.Serializer):
    qty = serializers.IntegerField(min_value=0, max_value=99)


class CheckoutSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(required=False, default="", allow_blank=True, max_length=120)
    name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=32)
    notes = serializers.CharField(required=False, default="", allow_blank=True, max_length=500)
    fulfillment_type = serializers.ChoiceField(
        choices=["pickup", "delivery"],
        default="pickup",
        required=False,
    )
    delivery_address = serializers.CharField(required=False, default="", allow_blank=True, max_length=500)
    delivery_address_structured = serializers.DictField(required=False, default=dict)
    saved_address_id = serializers.IntegerField(required=False, allow_null=True)
    delivery_complement = serializers.CharField(required=False, default="", allow_blank=True, max_length=200)
    delivery_instructions = serializers.CharField(required=False, default="", allow_blank=True, max_length=500)
    delivery_date = serializers.CharField(required=False, default="", allow_blank=True, max_length=32)
    delivery_time_slot = serializers.CharField(required=False, default="", allow_blank=True, max_length=32)
    payment_method = serializers.CharField(required=False, default="", allow_blank=True, max_length=32)
    use_loyalty = serializers.BooleanField(required=False, default=False)


class CheckoutResponseSerializer(serializers.Serializer):
    order_ref = serializers.CharField()
    status = serializers.CharField()
    next_url = serializers.CharField(required=False)


class DetailSerializer(serializers.Serializer):
    detail = serializers.CharField()


# ── Catalog ──────────────────────────────────────────────────────────


class AvailabilityBadgeSerializer(serializers.Serializer):
    label = serializers.CharField()
    css_class = serializers.CharField()
    can_add_to_cart = serializers.BooleanField()


class ProductListItemSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True, required=False)
    unit = serializers.CharField(allow_null=True, required=False)
    price_q = serializers.IntegerField(allow_null=True)
    price_display = serializers.CharField(allow_null=True)
    is_d1 = serializers.BooleanField()
    d1_price_display = serializers.CharField(allow_null=True)
    original_price_display = serializers.CharField(allow_null=True)
    badge = AvailabilityBadgeSerializer()
    promo_badge = serializers.DictField(allow_null=True, required=False)


@extend_schema_serializer(component_name="StorefrontCollection")
class CollectionSerializer(serializers.Serializer):
    ref = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_null=True, required=False)
    product_count = serializers.IntegerField()


class AvailabilityResponseSerializer(serializers.Serializer):
    ok = serializers.BooleanField()
    available_qty = serializers.CharField()
    badge_text = serializers.CharField()
    badge_class = serializers.CharField()
    is_bundle = serializers.BooleanField()


class ReverseGeocodeRequestSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class ReverseGeocodeResponseSerializer(serializers.Serializer):
    formatted_address = serializers.CharField()
    route = serializers.CharField()
    street_number = serializers.CharField()
    neighborhood = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    state_code = serializers.CharField()
    postal_code = serializers.CharField()
    country = serializers.CharField()
    country_code = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    place_id = serializers.CharField()


# ── Tracking ─────────────────────────────────────────────────────────


class TimelineEventSerializer(serializers.Serializer):
    label = serializers.CharField()
    event_type = serializers.CharField()
    timestamp_display = serializers.CharField()


class OrderItemSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    qty = serializers.IntegerField()
    unit_price_display = serializers.CharField()
    total_display = serializers.CharField()


class FulfillmentSerializer(serializers.Serializer):
    status = serializers.CharField()
    status_label = serializers.CharField()
    tracking_code = serializers.CharField(allow_null=True, allow_blank=True)
    tracking_url = serializers.CharField(allow_null=True)
    carrier = serializers.CharField(allow_null=True, allow_blank=True)
    dispatched_at = serializers.CharField(allow_null=True, allow_blank=True)
    delivered_at = serializers.CharField(allow_null=True, allow_blank=True)


class SurfaceActionSerializer(serializers.Serializer):
    ref = serializers.CharField()
    kind = serializers.CharField()
    label = serializers.CharField()
    priority = serializers.CharField()
    enabled = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True, required=False)
    href = serializers.CharField(allow_blank=True, required=False)
    method = serializers.CharField(allow_blank=True, required=False)
    payload_schema = serializers.DictField(required=False)
    idempotency = serializers.CharField(required=False)
    confirmation = serializers.DictField(required=False)


class OrderTrackingPromiseSerializer(serializers.Serializer):
    state = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()
    tone = serializers.CharField()
    deadline_at = serializers.CharField(allow_null=True, required=False)
    deadline_kind = serializers.CharField(allow_null=True, required=False)
    timer_mode = serializers.CharField()
    deadline_action = serializers.CharField()
    requires_active_notification = serializers.BooleanField()
    notification_topic = serializers.CharField(allow_null=True, required=False)
    actions = SurfaceActionSerializer(many=True, required=False)
    next_event = serializers.CharField(allow_blank=True, required=False)
    recovery = serializers.CharField(allow_blank=True, required=False)
    active_notification = serializers.CharField(allow_blank=True, required=False)


class OrderTrackingPromiseRowSerializer(serializers.Serializer):
    label = serializers.CharField()
    value = serializers.CharField()
    url = serializers.CharField(allow_null=True, required=False)


class OrderProgressStepSerializer(serializers.Serializer):
    label = serializers.CharField()
    key = serializers.CharField()
    state = serializers.CharField()
    timestamp_display = serializers.CharField(allow_null=True, required=False)


class PickupInfoSerializer(serializers.Serializer):
    address = serializers.CharField()
    opening_hours = serializers.CharField()
    google_maps_url = serializers.CharField(allow_null=True, required=False)


class OrderTrackingSerializer(serializers.Serializer):
    ref = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    status_color = serializers.CharField()
    promise = OrderTrackingPromiseSerializer()
    promise_rows = OrderTrackingPromiseRowSerializer(many=True)
    promise_deadline_label = serializers.CharField()
    progress_steps = OrderProgressStepSerializer(many=True)
    total_display = serializers.CharField()
    delivery_fee_display = serializers.CharField(allow_null=True, required=False)
    is_delivery = serializers.BooleanField()
    timeline = TimelineEventSerializer(many=True)
    items = OrderItemSerializer(many=True)
    fulfillments = FulfillmentSerializer(many=True)
    pickup_info = PickupInfoSerializer(allow_null=True, required=False)
    actions = SurfaceActionSerializer(many=True, required=False)
    is_active = serializers.BooleanField()
    server_now_iso = serializers.CharField()
    payment_pending = serializers.BooleanField()
    payment_expired = serializers.BooleanField()
    payment_confirmed = serializers.BooleanField()
    show_payment_confirmed_notice = serializers.BooleanField()
    payment_status = serializers.CharField(allow_null=True)
    payment_expires_at = serializers.CharField(allow_null=True, required=False)
    requires_payment_gate = serializers.BooleanField(required=False)
    payment_gate_url = serializers.CharField(allow_null=True, required=False)
    confirmation_countdown = serializers.BooleanField()
    confirmation_expires_at = serializers.CharField(allow_null=True, required=False)
    eta_display = serializers.CharField(allow_null=True, required=False)
    whatsapp_url = serializers.CharField(allow_blank=True, required=False)
    share_text = serializers.CharField(allow_blank=True, required=False)
    is_debug = serializers.BooleanField()
    last_updated_iso = serializers.CharField()
    last_updated_display = serializers.CharField()
    stale_after_seconds = serializers.IntegerField()


# ── Account ──────────────────────────────────────────────────────────


class CustomerProfileSerializer(serializers.Serializer):
    ref = serializers.CharField()
    name = serializers.CharField()
    first_name = serializers.CharField(allow_blank=True, required=False)
    last_name = serializers.CharField(allow_blank=True, required=False)
    phone = serializers.CharField()
    email = serializers.CharField(allow_null=True, allow_blank=True, required=False)
    birthday = serializers.CharField(allow_null=True, allow_blank=True, required=False)


class AddressSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    label = serializers.CharField()
    label_key = serializers.CharField(required=False, read_only=True)
    label_custom = serializers.CharField(allow_blank=True, required=False)
    formatted_address = serializers.CharField()
    complement = serializers.CharField(allow_blank=True, required=False)
    delivery_instructions = serializers.CharField(allow_blank=True, required=False)
    is_default = serializers.BooleanField()
    route = serializers.CharField(allow_blank=True, required=False)
    street_number = serializers.CharField(allow_blank=True, required=False)
    neighborhood = serializers.CharField(allow_blank=True, required=False)
    city = serializers.CharField(allow_blank=True, required=False)
    state_code = serializers.CharField(allow_blank=True, required=False)
    postal_code = serializers.CharField(allow_blank=True, required=False)
    latitude = serializers.FloatField(allow_null=True, required=False)
    longitude = serializers.FloatField(allow_null=True, required=False)
    place_id = serializers.CharField(allow_null=True, allow_blank=True, required=False)


class OrderHistoryItemSerializer(serializers.Serializer):
    ref = serializers.CharField()
    created_at = serializers.DateTimeField()
    created_at_display = serializers.CharField(required=False)
    total_display = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    status_color = serializers.CharField(required=False)
    item_count = serializers.IntegerField(required=False)
    actions = SurfaceActionSerializer(many=True, required=False)


class RemoteConversationSerializer(serializers.Serializer):
    order_ref = serializers.CharField()
    order_status = serializers.CharField()
    channel_ref = serializers.CharField()
    source_projection = serializers.CharField()
    state = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()
    tone = serializers.CharField()
    actions = SurfaceActionSerializer(many=True)
    deadline_at = serializers.CharField(allow_null=True, required=False)
    next_event = serializers.CharField(allow_blank=True, required=False)
    recovery = serializers.CharField(allow_blank=True, required=False)
    items_summary = serializers.ListField(child=serializers.CharField(), required=False)
    total_display = serializers.CharField()
    tracking_url = serializers.CharField()
    payment_url = serializers.CharField(allow_null=True, required=False)
    supports_access_link = serializers.BooleanField()
    requires_payment_gate = serializers.BooleanField()
