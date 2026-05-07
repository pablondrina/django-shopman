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


class CheckoutSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    phone = serializers.CharField(max_length=32)
    notes = serializers.CharField(required=False, default="", allow_blank=True, max_length=500)
    fulfillment_type = serializers.ChoiceField(
        choices=["pickup", "delivery"],
        default="pickup",
        required=False,
    )
    delivery_address = serializers.CharField(required=False, default="", allow_blank=True, max_length=500)


class CheckoutResponseSerializer(serializers.Serializer):
    order_ref = serializers.CharField()
    status = serializers.CharField()


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


class OrderTrackingSerializer(serializers.Serializer):
    ref = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
    total_display = serializers.CharField()
    timeline = TimelineEventSerializer(many=True)
    items = OrderItemSerializer(many=True)
    fulfillments = FulfillmentSerializer(many=True)
    payment_status = serializers.CharField(allow_null=True)


# ── Account ──────────────────────────────────────────────────────────


class CustomerProfileSerializer(serializers.Serializer):
    ref = serializers.CharField()
    name = serializers.CharField()
    phone = serializers.CharField()
    email = serializers.CharField(allow_null=True, allow_blank=True, required=False)


class AddressSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    label = serializers.CharField()
    formatted_address = serializers.CharField()
    complement = serializers.CharField(allow_blank=True, required=False)
    delivery_instructions = serializers.CharField(allow_blank=True, required=False)
    is_default = serializers.BooleanField()


class OrderHistoryItemSerializer(serializers.Serializer):
    ref = serializers.CharField()
    created_at = serializers.DateTimeField()
    total_display = serializers.CharField()
    status = serializers.CharField()
    status_label = serializers.CharField()
