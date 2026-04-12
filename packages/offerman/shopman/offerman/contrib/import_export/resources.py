"""Import/Export resources for Offerman models."""
from __future__ import annotations

from import_export import fields, resources
from import_export.widgets import ForeignKeyWidget

from shopman.offerman.models import Listing, ListingItem, Product


class ProductResource(resources.ModelResource):
    """Resource for Product import/export (CSV/XLSX).

    Import ID field: sku (upsert by SKU).
    """

    class Meta:
        model = Product
        fields = (
            "sku",
            "name",
            "base_price_q",
            "unit",
            "availability_policy",
            "is_published",
            "is_sellable",
            "shelf_life_days",
        )
        import_id_fields = ("sku",)
        export_order = fields


class ListingItemResource(resources.ModelResource):
    """Resource for ListingItem import/export (bulk price updates).

    Import ID fields: listing__ref + product__sku (upsert by composite key).
    """

    listing_ref = fields.Field(
        column_name="listing__ref",
        attribute="listing",
        widget=ForeignKeyWidget(Listing, field="ref"),
    )
    product_sku = fields.Field(
        column_name="product__sku",
        attribute="product",
        widget=ForeignKeyWidget(Product, field="sku"),
    )

    class Meta:
        model = ListingItem
        fields = (
            "listing_ref",
            "product_sku",
            "price_q",
            "min_qty",
            "is_published",
            "is_sellable",
        )
        import_id_fields = ("listing_ref", "product_sku")
        export_order = fields
