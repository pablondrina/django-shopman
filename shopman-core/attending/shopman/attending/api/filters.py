from __future__ import annotations

from django_filters import rest_framework as filters

from shopman.attending.models import Customer


class CustomerFilter(filters.FilterSet):
    group = filters.CharFilter(field_name="group__ref")

    class Meta:
        model = Customer
        fields = {
            "is_active": ["exact"],
        }
