from __future__ import annotations

from rest_framework import serializers

from shopman.attending.models import ContactPoint, Customer, CustomerAddress


class ContactPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactPoint
        fields = ["type", "value_normalized", "is_primary", "is_verified"]


class CustomerAddressSerializer(serializers.ModelSerializer):
    short_address = serializers.CharField(read_only=True)
    display_label = serializers.CharField(read_only=True)

    class Meta:
        model = CustomerAddress
        fields = [
            "id",
            "label",
            "label_custom",
            "formatted_address",
            "short_address",
            "display_label",
            "complement",
            "delivery_instructions",
            "latitude",
            "longitude",
            "is_default",
        ]


class CreateAddressSerializer(serializers.Serializer):
    label = serializers.ChoiceField(choices=["home", "work", "other"])
    formatted_address = serializers.CharField(max_length=500)
    label_custom = serializers.CharField(max_length=50, required=False, default="")
    complement = serializers.CharField(max_length=100, required=False, default="")
    delivery_instructions = serializers.CharField(required=False, default="")
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    is_default = serializers.BooleanField(required=False, default=False)


class CustomerSerializer(serializers.ModelSerializer):
    group_name = serializers.CharField(source="group.name", read_only=True, default=None)
    listing_code = serializers.CharField(read_only=True)
    phone_display = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = [
            "ref",
            "uuid",
            "first_name",
            "last_name",
            "customer_type",
            "phone",
            "phone_display",
            "email",
            "group_name",
            "listing_code",
            "is_active",
        ]

    def get_phone_display(self, obj) -> str:
        """Formata telefone E.164 para exibição: +5543984049009 → (43) 98404-9009"""
        phone = obj.phone or ""
        if phone.startswith("+55") and len(phone) == 14:
            # +55 DD 9XXXX XXXX
            ddd = phone[3:5]
            part1 = phone[5:10]
            part2 = phone[10:14]
            return f"({ddd}) {part1}-{part2}"
        if phone.startswith("+55") and len(phone) == 13:
            # +55 DD XXXX XXXX (fixo)
            ddd = phone[3:5]
            part1 = phone[5:9]
            part2 = phone[9:13]
            return f"({ddd}) {part1}-{part2}"
        return phone


class CustomerDetailSerializer(CustomerSerializer):
    contacts = ContactPointSerializer(many=True, source="contact_points", read_only=True)
    addresses = CustomerAddressSerializer(many=True, read_only=True)

    class Meta(CustomerSerializer.Meta):
        fields = CustomerSerializer.Meta.fields + ["contacts", "addresses", "notes"]


class CreateCustomerSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100)
    last_name = serializers.CharField(max_length=100, required=False, default="")
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, default="")
    customer_type = serializers.ChoiceField(choices=["individual", "business"], required=False, default="individual")
    group_ref = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")


class UpdateCustomerSerializer(serializers.Serializer):
    first_name = serializers.CharField(max_length=100, required=False)
    last_name = serializers.CharField(max_length=100, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    group_ref = serializers.CharField(max_length=50, required=False, allow_blank=True)


class CustomerInsightSerializer(serializers.Serializer):
    total_orders = serializers.IntegerField()
    total_spent_q = serializers.IntegerField()
    average_ticket_q = serializers.IntegerField()
    rfm_segment = serializers.CharField()
    is_vip = serializers.BooleanField()
    is_at_risk = serializers.BooleanField()
    days_since_last_order = serializers.IntegerField(allow_null=True)
    favorite_products = serializers.JSONField()
    rfm_recency = serializers.IntegerField(allow_null=True)
    rfm_frequency = serializers.IntegerField(allow_null=True)
    rfm_monetary = serializers.IntegerField(allow_null=True)


class InsightsSummarySerializer(serializers.Serializer):
    total_customers = serializers.IntegerField()
    total_vip = serializers.IntegerField()
    total_at_risk = serializers.IntegerField()
    avg_ticket_q = serializers.IntegerField()
    segments_distribution = serializers.DictField(child=serializers.IntegerField())
