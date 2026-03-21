"""
Shopman Accounting API — Serializers.
"""

from __future__ import annotations

from rest_framework import serializers


class AccountEntrySerializer(serializers.Serializer):
    """Serializer para AccountEntry."""

    entry_id = serializers.CharField()
    description = serializers.CharField()
    amount_q = serializers.IntegerField()
    type = serializers.CharField()
    category = serializers.CharField()
    date = serializers.DateField()
    due_date = serializers.DateField(allow_null=True)
    paid_date = serializers.DateField(allow_null=True)
    status = serializers.CharField()
    reference = serializers.CharField(allow_null=True)
    customer_name = serializers.CharField(allow_null=True)
    supplier_name = serializers.CharField(allow_null=True)


class CashFlowSummarySerializer(serializers.Serializer):
    """Serializer para CashFlowSummary."""

    period_start = serializers.DateField()
    period_end = serializers.DateField()
    total_revenue_q = serializers.IntegerField()
    total_expenses_q = serializers.IntegerField()
    net_q = serializers.IntegerField()
    balance_q = serializers.IntegerField()
    revenue_by_category = serializers.DictField(child=serializers.IntegerField())
    expenses_by_category = serializers.DictField(child=serializers.IntegerField())


class AccountsSummarySerializer(serializers.Serializer):
    """Serializer para AccountsSummary."""

    total_receivable_q = serializers.IntegerField()
    total_payable_q = serializers.IntegerField()
    overdue_receivable_q = serializers.IntegerField()
    overdue_payable_q = serializers.IntegerField()
    receivables = AccountEntrySerializer(many=True)
    payables = AccountEntrySerializer(many=True)


class CreatePayableSerializer(serializers.Serializer):
    """Serializer de input para criação de conta a pagar."""

    description = serializers.CharField(max_length=255)
    amount_q = serializers.IntegerField(min_value=1)
    due_date = serializers.DateField()
    category = serializers.CharField(max_length=64)
    supplier_name = serializers.CharField(max_length=255, required=False, allow_blank=True)
    reference = serializers.CharField(max_length=128, required=False, allow_blank=True)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True)


class CreateEntryResultSerializer(serializers.Serializer):
    """Serializer para CreateEntryResult."""

    success = serializers.BooleanField()
    entry_id = serializers.CharField(allow_null=True)
    error_message = serializers.CharField(allow_null=True)
