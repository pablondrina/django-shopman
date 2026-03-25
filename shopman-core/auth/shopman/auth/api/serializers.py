from __future__ import annotations

from rest_framework import serializers


class RequestCodeSerializer(serializers.Serializer):
    phone = serializers.CharField()
    delivery_method = serializers.ChoiceField(
        choices=["whatsapp", "sms", "email"],
        default="whatsapp",
        required=False,
    )


class RequestCodeResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    code_id = serializers.CharField(allow_null=True)
    expires_at = serializers.CharField(allow_null=True)


class VerifyCodeSerializer(serializers.Serializer):
    phone = serializers.CharField()
    code = serializers.CharField(max_length=6)


class VerifyCodeResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    customer_id = serializers.UUIDField(allow_null=True)
    created_customer = serializers.BooleanField()
