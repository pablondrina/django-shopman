from __future__ import annotations

from rest_framework import serializers


class RequestCodeSerializer(serializers.Serializer):
    target = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    delivery_method = serializers.ChoiceField(
        choices=["whatsapp", "sms", "email"],
        default="whatsapp",
        required=False,
    )

    def validate(self, attrs):
        attrs = super().validate(attrs)
        target = attrs.get("target") or attrs.get("phone")
        if not target:
            raise serializers.ValidationError({"target": "This field is required."})
        attrs["target"] = target
        return attrs


class RequestCodeResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    code_id = serializers.CharField(allow_null=True)
    expires_at = serializers.CharField(allow_null=True)


class VerifyCodeSerializer(serializers.Serializer):
    target = serializers.CharField(required=False)
    phone = serializers.CharField(required=False)
    code = serializers.CharField(max_length=6)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        target = attrs.get("target") or attrs.get("phone")
        if not target:
            raise serializers.ValidationError({"target": "This field is required."})
        attrs["target"] = target
        return attrs


class VerifyCodeResponseSerializer(serializers.Serializer):
    success = serializers.BooleanField()
    customer_id = serializers.UUIDField(allow_null=True)
    created_customer = serializers.BooleanField()
