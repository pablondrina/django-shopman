"""Tests for shopman.offering.contrib.import_export resources."""
from __future__ import annotations

from decimal import Decimal
from io import StringIO

import pytest
from import_export.formats.base_formats import CSV

from shopman.offering.contrib.import_export.resources import ListingItemResource, ProductResource
from shopman.offering.models import Listing, ListingItem, Product


@pytest.fixture
def csv_format():
    return CSV()


class TestProductResource:
    """Tests for ProductResource import/export."""

    def test_export_products(self, db, product, croissant, csv_format):
        """Export existing products to CSV."""
        resource = ProductResource()
        dataset = resource.export()
        assert len(dataset) >= 2
        # Check headers
        assert "sku" in dataset.headers
        assert "name" in dataset.headers
        assert "base_price_q" in dataset.headers

    def test_export_fields_match_spec(self, db, product, csv_format):
        """Exported fields match the spec (sku, name, base_price_q, unit, etc.)."""
        resource = ProductResource()
        dataset = resource.export()
        expected_headers = {
            "sku", "name", "base_price_q", "unit",
            "availability_policy", "is_published", "is_available", "shelf_life_days",
        }
        assert set(dataset.headers) == expected_headers

    def test_import_new_product(self, db, csv_format):
        """Import a new product via CSV."""
        csv_data = (
            "sku,name,base_price_q,unit,availability_policy,is_published,is_available,shelf_life_days\r\n"
            "PAIN-CHOC,Pain au Chocolat,1250,un,planned_ok,1,1,24\r\n"
        )
        resource = ProductResource()
        dataset = csv_format.create_dataset(StringIO(csv_data))
        result = resource.import_data(dataset, dry_run=False)

        assert not result.has_errors(), f"Import errors: {result.row_errors()}"
        assert Product.objects.filter(sku="PAIN-CHOC").exists()
        p = Product.objects.get(sku="PAIN-CHOC")
        assert p.name == "Pain au Chocolat"
        assert p.base_price_q == 1250
        assert p.shelf_life_days == 24

    def test_import_update_existing(self, db, product, csv_format):
        """Import updates existing product by SKU."""
        csv_data = (
            "sku,name,base_price_q,unit,availability_policy,is_published,is_available,shelf_life_days\r\n"
            f"{product.sku},Baguete Premium,750,un,planned_ok,1,1,\r\n"
        )
        resource = ProductResource()
        dataset = csv_format.create_dataset(StringIO(csv_data))
        result = resource.import_data(dataset, dry_run=False)

        assert not result.has_errors(), f"Import errors: {result.row_errors()}"
        product.refresh_from_db()
        assert product.name == "Baguete Premium"
        assert product.base_price_q == 750

    def test_import_dry_run(self, db, csv_format):
        """Dry run does not persist changes."""
        csv_data = (
            "sku,name,base_price_q,unit,availability_policy,is_published,is_available,shelf_life_days\r\n"
            "DRY-RUN,Test Dry Run,100,un,stock_only,1,1,\r\n"
        )
        resource = ProductResource()
        dataset = csv_format.create_dataset(StringIO(csv_data))
        result = resource.import_data(dataset, dry_run=True)

        assert not result.has_errors()
        assert not Product.objects.filter(sku="DRY-RUN").exists()

    def test_roundtrip_export_import(self, db, product, croissant, csv_format):
        """Export then re-import should be idempotent."""
        resource = ProductResource()
        initial_count = Product.objects.count()
        dataset = resource.export()
        csv_content = csv_format.export_data(dataset)

        # Re-import
        reimport_dataset = csv_format.create_dataset(StringIO(csv_content))
        result = resource.import_data(reimport_dataset, dry_run=False)
        assert not result.has_errors(), f"Import errors: {result.row_errors()}"
        # Count unchanged
        assert Product.objects.count() == initial_count


class TestListingItemResource:
    """Tests for ListingItemResource import/export."""

    def test_export_listing_items(self, db, listing_item, csv_format):
        """Export listing items to CSV."""
        resource = ListingItemResource()
        dataset = resource.export()
        assert len(dataset) == 1
        assert "listing__code" in dataset.headers
        assert "product__sku" in dataset.headers
        assert "price_q" in dataset.headers

    def test_export_fields_match_spec(self, db, listing_item, csv_format):
        """Exported fields match the spec."""
        resource = ListingItemResource()
        dataset = resource.export()
        expected_headers = {
            "listing__code", "product__sku", "price_q",
            "min_qty", "is_published", "is_available",
        }
        assert set(dataset.headers) == expected_headers

    def test_import_new_listing_item(self, db, listing, croissant, csv_format):
        """Import a new listing item via CSV."""
        csv_data = (
            "listing__code,product__sku,price_q,min_qty,is_published,is_available\r\n"
            f"{listing.code},{croissant.sku},1000,1.000,1,1\r\n"
        )
        resource = ListingItemResource()
        dataset = csv_format.create_dataset(StringIO(csv_data))
        result = resource.import_data(dataset, dry_run=False)

        assert not result.has_errors(), f"Import errors: {result.row_errors()}"
        item = ListingItem.objects.get(listing=listing, product=croissant)
        assert item.price_q == 1000

    def test_import_update_price(self, db, listing_item, csv_format):
        """Import updates existing listing item price."""
        old_price = listing_item.price_q
        new_price = old_price + 200
        csv_data = (
            "listing__code,product__sku,price_q,min_qty,is_published,is_available\r\n"
            f"{listing_item.listing.code},{listing_item.product.sku},{new_price},"
            f"{listing_item.min_qty},1,1\r\n"
        )
        resource = ListingItemResource()
        dataset = csv_format.create_dataset(StringIO(csv_data))
        result = resource.import_data(dataset, dry_run=False)

        assert not result.has_errors(), f"Import errors: {result.row_errors()}"
        listing_item.refresh_from_db()
        assert listing_item.price_q == new_price

    def test_roundtrip_export_import(self, db, listing_item, csv_format):
        """Export then re-import should be idempotent."""
        resource = ListingItemResource()
        dataset = resource.export()
        csv_content = csv_format.export_data(dataset)

        reimport_dataset = csv_format.create_dataset(StringIO(csv_content))
        result = resource.import_data(reimport_dataset, dry_run=False)
        assert not result.has_errors(), f"Import errors: {result.row_errors()}"
        assert ListingItem.objects.count() == 1
