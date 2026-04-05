from __future__ import annotations

from rest_framework import serializers

from shopman.ordering.models import Channel, Directive, Order, Session


class ChannelSerializer(serializers.ModelSerializer):
    class Meta:
        model = Channel
        fields = ("id", "ref", "name", "pricing_policy", "edit_policy", "display_order", "config", "is_active")


class SessionSerializer(serializers.ModelSerializer):
    channel_ref = serializers.CharField(source="channel.ref", read_only=True)

    class Meta:
        model = Session
        fields = (
            "id",
            "session_key",
            "channel",
            "channel_ref",
            "handle_type",
            "handle_ref",
            "state",
            "pricing_policy",
            "edit_policy",
            "rev",
            "items",
            "data",
            "opened_at",
            "committed_at",
            "updated_at",
        )


class SessionCreateSerializer(serializers.Serializer):
    """
    POST /api/sessions

    v0.5.7 (Core do framework): permite abrir/criar sessão.
    v0.5.8: permanece válido (não conflita com kernel minimalista).

    Notas:
    - `channel_ref` usa SlugRelatedField para renderizar <select> na Browsable API.
    - Se `handle_type` e `handle_ref` forem enviados, a API tenta get-or-open (1 sessão open por owner).
    """

    channel_ref = serializers.SlugRelatedField(
        slug_field="ref",
        queryset=Channel.objects.all(),
        source="channel",
    )
    session_key = serializers.CharField(required=False, allow_blank=False, max_length=64)
    handle_type = serializers.CharField(required=False, allow_blank=False, max_length=32)
    handle_ref = serializers.CharField(required=False, allow_blank=False, max_length=64)


class OperationSerializer(serializers.Serializer):
    """
    Serializer para validação de operações individuais.

    Operações suportadas:
    - add_line: {op, sku, qty, unit_price_q?, meta?}
    - remove_line: {op, line_id}
    - set_qty: {op, line_id, qty}
    - replace_sku: {op, line_id, sku, unit_price_q?, meta?}
    - set_data: {op, path, value}
    - merge_lines: {op, from_line_id, into_line_id}
    """

    SUPPORTED_OPS = {"add_line", "remove_line", "set_qty", "replace_sku", "set_data", "merge_lines"}

    # Paths permitidos para set_data
    # Paths que começam com estes prefixos são permitidos
    ALLOWED_DATA_PATHS = {
        "customer",      # customer.name, customer.phone, etc
        "delivery",      # delivery.address, delivery.notes, etc
        "payment",       # payment.method, payment.installments, etc
        "notes",         # notes (string simples)
        "meta",          # meta.* (dados arbitrários)
        "extra",         # extra.* (dados extras)
        "custom",        # custom.* (dados customizados)
        "tags",          # tags (lista)
        "discounts",     # discounts.* (descontos aplicados)
        "fees",          # fees.* (taxas)
        "tip",           # tip (gorjeta)
        "coupon",        # coupon.* (cupom aplicado)
        "source",        # source.* (origem do pedido)
        "operator",      # operator.* (operador/vendedor)
        "table",         # table (mesa - restaurantes)
        "tab",           # tab (comanda)
    }

    # Paths explicitamente proibidos (críticos do sistema)
    FORBIDDEN_DATA_PATHS = {
        "checks",        # Gerenciado pelo sistema
        "issues",        # Gerenciado pelo sistema
        "state",         # Campo do model
        "status",        # Campo do model
        "rev",           # Campo do model
        "session_key",   # Campo do model
        "channel",       # Campo do model
        "items",         # Gerenciado via operações específicas
        "pricing",       # Gerenciado pelo sistema
        "pricing_trace", # Gerenciado pelo sistema
        "__",            # Dunder attributes
    }

    op = serializers.CharField()
    sku = serializers.CharField(required=False, allow_blank=False)
    qty = serializers.DecimalField(required=False, max_digits=12, decimal_places=3)
    line_id = serializers.CharField(required=False, allow_blank=False)
    unit_price_q = serializers.IntegerField(required=False)
    meta = serializers.DictField(required=False)
    path = serializers.CharField(required=False, allow_blank=False, max_length=128)
    value = serializers.JSONField(required=False)
    from_line_id = serializers.CharField(required=False, allow_blank=False)
    into_line_id = serializers.CharField(required=False, allow_blank=False)

    def validate_op(self, value: str) -> str:
        if value not in self.SUPPORTED_OPS:
            raise serializers.ValidationError(
                f"Operação '{value}' não suportada. Operações válidas: {', '.join(sorted(self.SUPPORTED_OPS))}"
            )
        return value

    def validate_path(self, value: str) -> str:
        """Valida path para operação set_data."""
        if not value:
            return value

        # Normaliza path
        path = value.strip().lower()

        # Verifica paths proibidos
        root_path = path.split(".")[0]
        if root_path in self.FORBIDDEN_DATA_PATHS or path.startswith("__"):
            raise serializers.ValidationError(
                f"Path '{value}' não permitido. Este campo é gerenciado pelo sistema."
            )

        # Verifica se está na whitelist
        if root_path not in self.ALLOWED_DATA_PATHS:
            allowed = ", ".join(sorted(self.ALLOWED_DATA_PATHS))
            raise serializers.ValidationError(
                f"Path '{value}' não permitido. Paths válidos começam com: {allowed}"
            )

        # Limita profundidade (máximo 5 níveis)
        depth = len(path.split("."))
        if depth > 5:
            raise serializers.ValidationError(
                f"Path muito profundo ({depth} níveis). Máximo permitido: 5"
            )

        return value

    def validate(self, attrs: dict) -> dict:
        op = attrs.get("op")

        if op == "add_line":
            if not attrs.get("sku"):
                raise serializers.ValidationError({"sku": "Campo obrigatório para add_line"})
            if attrs.get("qty") is None:
                raise serializers.ValidationError({"qty": "Campo obrigatório para add_line"})

        elif op == "remove_line":
            if not attrs.get("line_id"):
                raise serializers.ValidationError({"line_id": "Campo obrigatório para remove_line"})

        elif op == "set_qty":
            if not attrs.get("line_id"):
                raise serializers.ValidationError({"line_id": "Campo obrigatório para set_qty"})
            if attrs.get("qty") is None:
                raise serializers.ValidationError({"qty": "Campo obrigatório para set_qty"})

        elif op == "replace_sku":
            if not attrs.get("line_id"):
                raise serializers.ValidationError({"line_id": "Campo obrigatório para replace_sku"})
            if not attrs.get("sku"):
                raise serializers.ValidationError({"sku": "Campo obrigatório para replace_sku"})

        elif op == "set_data":
            if not attrs.get("path"):
                raise serializers.ValidationError({"path": "Campo obrigatório para set_data"})
            if "value" not in attrs:
                raise serializers.ValidationError({"value": "Campo obrigatório para set_data"})

        elif op == "merge_lines":
            if not attrs.get("from_line_id"):
                raise serializers.ValidationError({"from_line_id": "Campo obrigatório para merge_lines"})
            if not attrs.get("into_line_id"):
                raise serializers.ValidationError({"into_line_id": "Campo obrigatório para merge_lines"})

        return attrs


class SessionModifySerializer(serializers.Serializer):
    """
    POST /api/sessions/<session_key>/modify

    Aplica operações a uma sessão. Operações são validadas individualmente.
    """

    channel_ref = serializers.SlugRelatedField(
        slug_field="ref",
        queryset=Channel.objects.all(),
        source="channel",
    )
    ops = serializers.ListField(child=OperationSerializer(), allow_empty=False)


class SessionResolveSerializer(serializers.Serializer):
    """
    POST /api/sessions/<session_key>/resolve

    v0.5.8: resolução delegada por `issue["source"]` para IssueResolver.
    """

    channel_ref = serializers.SlugRelatedField(
        slug_field="ref",
        queryset=Channel.objects.all(),
        source="channel",
    )
    issue_id = serializers.CharField(allow_blank=False, max_length=64)
    action_id = serializers.CharField(allow_blank=False, max_length=64)


class SessionCommitSerializer(serializers.Serializer):
    """
    POST /api/sessions/<session_key>/commit
    """

    channel_ref = serializers.SlugRelatedField(
        slug_field="ref",
        queryset=Channel.objects.all(),
        source="channel",
    )
    idempotency_key = serializers.CharField(required=False, allow_blank=False, max_length=128)


class OrderSerializer(serializers.ModelSerializer):
    channel_ref = serializers.CharField(source="channel.ref", read_only=True)

    class Meta:
        model = Order
        fields = ("id", "ref", "channel", "channel_ref", "status", "created_at")


class DirectiveSerializer(serializers.ModelSerializer):
    class Meta:
        model = Directive
        fields = ("id", "topic", "status", "attempts", "created_at", "updated_at")
