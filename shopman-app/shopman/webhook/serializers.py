"""
Serializers para webhook inbound do Manychat.

O Manychat envia payloads com subscriber_id, custom_fields e last_input_text.
Cada action tem seu próprio serializer de validação.
"""

from __future__ import annotations

from rest_framework import serializers


class ManychatInboundSerializer(serializers.Serializer):
    """
    Valida payload do Manychat (custom action / external request).

    Campos obrigatórios:
    - action: ação a executar (new_order, add_item, commit_order, check_status, list_menu)
    - subscriber_id: Manychat subscriber ID (string ou int)

    Campos opcionais (depende da action):
    - custom_fields: dict com custom fields do Manychat
    - last_input_text: último texto digitado pelo usuário
    - data: dados adicionais da action
    """

    ACTION_CHOICES = [
        ("new_order", "Novo pedido"),
        ("add_item", "Adicionar item"),
        ("commit_order", "Fechar pedido"),
        ("check_status", "Consultar status"),
        ("list_menu", "Listar cardápio"),
    ]

    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    subscriber_id = serializers.CharField()
    custom_fields = serializers.DictField(required=False, default=dict)
    last_input_text = serializers.CharField(required=False, allow_blank=True, default="")
    data = serializers.DictField(required=False, default=dict)


class NewOrderSerializer(serializers.Serializer):
    """Valida data para action new_order."""

    customer_phone = serializers.CharField(required=False, allow_blank=True, default="")
    customer_name = serializers.CharField(required=False, allow_blank=True, default="")
    items = serializers.ListField(
        child=serializers.DictField(),
        required=False,
        default=list,
    )

    def validate_items(self, value: list) -> list:
        for item in value:
            if "sku" not in item:
                raise serializers.ValidationError("Cada item precisa de 'sku'.")
            if "qty" not in item:
                raise serializers.ValidationError("Cada item precisa de 'qty'.")
        return value


class AddItemSerializer(serializers.Serializer):
    """Valida data para action add_item."""

    session_key = serializers.CharField()
    sku = serializers.CharField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=3)
    unit_price_q = serializers.IntegerField(required=False)


class CommitOrderSerializer(serializers.Serializer):
    """Valida data para action commit_order."""

    session_key = serializers.CharField()


class CheckStatusSerializer(serializers.Serializer):
    """Valida data para action check_status."""

    order_ref = serializers.CharField()
