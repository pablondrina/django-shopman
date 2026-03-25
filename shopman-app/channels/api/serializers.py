from __future__ import annotations

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
    sku = serializers.CharField()
    qty = serializers.IntegerField(min_value=1, default=1)


class UpdateItemSerializer(serializers.Serializer):
    qty = serializers.IntegerField(min_value=1)


class CheckoutSerializer(serializers.Serializer):
    name = serializers.CharField()
    phone = serializers.CharField()
    notes = serializers.CharField(required=False, default="", allow_blank=True)
    fulfillment_type = serializers.ChoiceField(
        choices=["pickup", "delivery"],
        default="pickup",
        required=False,
    )
    delivery_address = serializers.CharField(required=False, default="", allow_blank=True)


class CheckoutResponseSerializer(serializers.Serializer):
    order_ref = serializers.CharField()
    order_id = serializers.IntegerField()
    status = serializers.CharField()
