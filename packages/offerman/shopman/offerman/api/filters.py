from __future__ import annotations

from django_filters import rest_framework as filters

from shopman.offerman.models import Collection, Listing, ListingItem, Product


class ProductFilter(filters.FilterSet):
    collection = filters.CharFilter(method="filter_collection")

    class Meta:
        model = Product
        fields = {
            "is_published": ["exact"],
            "is_available": ["exact"],
            "unit": ["exact"],
        }

    def filter_collection(self, queryset, name, value):
        return queryset.filter(collection_items__collection__ref=value)


class CollectionFilter(filters.FilterSet):
    class Meta:
        model = Collection
        fields = {
            "is_active": ["exact"],
        }


class ListingFilter(filters.FilterSet):
    class Meta:
        model = Listing
        fields = {
            "is_active": ["exact"],
        }


class ListingItemFilter(filters.FilterSet):
    sku = filters.CharFilter(field_name="product__sku")

    class Meta:
        model = ListingItem
        fields = ["sku"]
