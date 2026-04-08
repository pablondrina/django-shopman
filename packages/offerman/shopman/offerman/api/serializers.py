from __future__ import annotations

from rest_framework import serializers

from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product, ProductComponent


class ProductSerializer(serializers.ModelSerializer):
    keywords = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "uuid",
            "sku",
            "name",
            "short_description",
            "unit",
            "base_price_q",
            "is_published",
            "is_available",
            "availability_policy",
            "keywords",
        ]

    def get_keywords(self, obj: Product) -> list[str]:
        return list(obj.keywords.names())


class ProductComponentSerializer(serializers.ModelSerializer):
    component_sku = serializers.CharField(source="component.sku")
    unit_of_measure = serializers.CharField(source="component.unit")

    class Meta:
        model = ProductComponent
        fields = ["component_sku", "qty", "unit_of_measure"]


class ProductDetailSerializer(ProductSerializer):
    components = ProductComponentSerializer(many=True, read_only=True)

    class Meta(ProductSerializer.Meta):
        fields = ProductSerializer.Meta.fields + [
            "long_description",
            "shelf_life_days",
            "production_cycle_hours",
            "components",
        ]


class CollectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Collection
        fields = ["uuid", "slug", "name", "description", "is_active"]


class CollectionDetailSerializer(CollectionSerializer):
    products = serializers.SerializerMethodField()

    class Meta(CollectionSerializer.Meta):
        fields = CollectionSerializer.Meta.fields + ["products"]

    def get_products(self, obj: Collection) -> list[dict]:
        items = obj.items.select_related("product").order_by("sort_order")
        return [
            {
                "sku": item.product.sku,
                "name": item.product.name,
                "is_primary": item.is_primary,
                "sort_order": item.sort_order,
            }
            for item in items
        ]


class ListingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Listing
        fields = ["uuid", "ref", "name", "description", "is_active", "priority"]


class ListingItemSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku")
    product_name = serializers.CharField(source="product.name")

    class Meta:
        model = ListingItem
        fields = ["sku", "product_name", "price_q", "min_qty", "is_published", "is_available"]


class PriceResponseSerializer(serializers.Serializer):
    sku = serializers.CharField()
    name = serializers.CharField()
    unit_price_q = serializers.IntegerField()
    total_q = serializers.IntegerField()
    currency = serializers.CharField()
    listing_ref = serializers.CharField(allow_null=True)
