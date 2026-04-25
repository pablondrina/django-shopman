from __future__ import annotations

from rest_framework import serializers
from shopman.payman.models.intent import PaymentIntent
from shopman.payman.models.transaction import PaymentTransaction


class PaymentTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentTransaction
        fields = ["id", "type", "amount_q", "gateway_id", "created_at"]


class PaymentIntentSerializer(serializers.ModelSerializer):
    transactions = PaymentTransactionSerializer(many=True, read_only=True)

    class Meta:
        model = PaymentIntent
        fields = [
            "ref",
            "order_ref",
            "method",
            "status",
            "amount_q",
            "currency",
            "gateway",
            "gateway_id",
            "created_at",
            "authorized_at",
            "captured_at",
            "cancelled_at",
            "expires_at",
            "cancel_reason",
            "transactions",
        ]


class PaymentIntentListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentIntent
        fields = [
            "ref",
            "order_ref",
            "method",
            "status",
            "amount_q",
            "currency",
            "created_at",
        ]
