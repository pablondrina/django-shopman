"""Tests for Offerman models."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from shopman.offerman.models import (
    Collection,
    CollectionItem,
    Product,
    ProductComponent,
    Listing,
    ListingItem,
)


pytestmark = pytest.mark.django_db


class TestProduct:
    """Tests for Product model."""

    def test_create_product(self, db):
        product = Product.objects.create(
            sku="BAGUETE",
            name="Baguete Artesanal",
            base_price_q=500,
        )
        assert product.sku == "BAGUETE"
        assert product.base_price_q == 500
        assert product.is_published is True
        assert product.is_available is True

    def test_base_price_property(self, db):
        product = Product.objects.create(
            sku="TEST",
            name="Test",
            base_price_q=500,
        )
        assert product.base_price == Decimal("5.00")

        product.base_price = Decimal("7.50")
        assert product.base_price_q == 750

    def test_queryset_active_method(self, db):
        Product.objects.create(sku="P1", name="P1")
        Product.objects.create(sku="P2", name="P2", is_published=False)
        Product.objects.create(sku="P3", name="P3", is_available=False)

        active = Product.objects.active()
        assert active.count() == 1
        assert active.first().sku == "P1"

    def test_queryset_published_method(self, db):
        Product.objects.create(sku="P1", name="P1")
        Product.objects.create(sku="P2", name="P2", is_published=False)

        published = Product.objects.published()
        assert published.count() == 1
        assert published.first().sku == "P1"

    def test_queryset_available_method(self, db):
        Product.objects.create(sku="P1", name="P1")
        Product.objects.create(sku="P2", name="P2", is_available=False)

        available = Product.objects.available()
        assert available.count() == 1
        assert available.first().sku == "P1"

    def test_is_bundle_property(self, db):
        product = Product.objects.create(sku="SINGLE", name="Single")
        combo = Product.objects.create(sku="COMBO", name="Combo")
        croissant = Product.objects.create(sku="CROISSANT", name="Croissant")

        ProductComponent.objects.create(parent=combo, component=croissant, qty=Decimal("2"))

        assert product.is_bundle is False
        assert combo.is_bundle is True

    def test_margin_percent_with_cost_backend(self, db):
        from unittest.mock import MagicMock
        from shopman.offerman.conf import reset_cost_backend
        import shopman.offerman.conf as conf

        product = Product.objects.create(
            sku="MARGIN-TEST",
            name="Margin Test",
            base_price_q=1000,
        )

        mock_backend = MagicMock()
        mock_backend.get_cost.return_value = 700
        original = conf._cost_backend_instance
        conf._cost_backend_instance = mock_backend

        try:
            assert product.margin_percent == Decimal("30.0")
            mock_backend.get_cost.assert_called_with("MARGIN-TEST")
        finally:
            conf._cost_backend_instance = original

    def test_margin_percent_no_cost_backend(self, db):
        product = Product.objects.create(sku="NO-COST", name="No Cost")
        assert product.margin_percent is None

    def test_is_perishable_with_shelf_life(self, db):
        product = Product.objects.create(
            sku="PERISHABLE",
            name="Perishable",
            shelf_life_days=12,
        )
        assert product.is_perishable is True

    def test_is_perishable_without_shelf_life(self, db):
        product = Product.objects.create(sku="DURABLE", name="Durable")
        assert product.is_perishable is False

    def test_production_cycle_hours(self, db):
        product = Product.objects.create(
            sku="BREAD",
            name="Bread",
            production_cycle_hours=4,
        )
        assert product.production_cycle_hours == 4

    def test_shelf_life_days(self, db):
        product = Product.objects.create(
            sku="CROISSANT-SL",
            name="Croissant",
            shelf_life_days=12,
        )
        assert product.shelf_life_days == 12


class TestProductComponent:
    def test_create_component(self, db):
        combo = Product.objects.create(sku="COMBO", name="Combo")
        croissant = Product.objects.create(sku="CROISSANT", name="Croissant")

        comp = ProductComponent.objects.create(
            parent=combo,
            component=croissant,
            qty=Decimal("2"),
        )
        assert comp.component == croissant
        assert comp.qty == Decimal("2")

    def test_self_reference_validation(self, db):
        product = Product.objects.create(sku="SELF", name="Self")
        with pytest.raises(ValidationError):
            ProductComponent.objects.create(
                parent=product,
                component=product,
                qty=Decimal("1"),
            )

    def test_circular_reference_validation(self, db):
        a = Product.objects.create(sku="A", name="A")
        b = Product.objects.create(sku="B", name="B")
        c = Product.objects.create(sku="C", name="C")

        ProductComponent.objects.create(parent=a, component=b, qty=Decimal("1"))
        ProductComponent.objects.create(parent=b, component=c, qty=Decimal("1"))

        with pytest.raises(ValidationError):
            ProductComponent.objects.create(parent=c, component=a, qty=Decimal("1"))


class TestListing:
    def test_create_listing(self, db):
        listing = Listing.objects.create(
            ref="ifood",
            name="iFood",
        )
        assert listing.ref == "ifood"
        assert listing.is_active is True

    def test_is_valid(self, db):
        from datetime import date, timedelta

        listing = Listing.objects.create(
            ref="seasonal",
            name="Seasonal",
            valid_from=date.today() - timedelta(days=1),
            valid_until=date.today() + timedelta(days=1),
        )
        assert listing.is_valid() is True

        listing.valid_until = date.today() - timedelta(days=1)
        assert listing.is_valid() is False

    def test_is_valid_inactive(self, db):
        listing = Listing.objects.create(ref="inactive", name="Inactive", is_active=False)
        assert listing.is_valid() is False


class TestListingItem:
    def test_create_item(self, db):
        listing = Listing.objects.create(ref="default", name="Default")
        product = Product.objects.create(sku="PROD", name="Product")

        item = ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=600,
        )
        assert item.price_q == 600
        assert item.price == Decimal("6.00")

    def test_visibility_flags(self, db):
        listing = Listing.objects.create(ref="test", name="Test")
        product = Product.objects.create(sku="PROD", name="Product")

        item = ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=500,
            is_published=False,
            is_available=True,
        )
        assert item.is_published is False
        assert item.is_available is True


class TestCollection:
    def test_create_collection(self, db):
        collection = Collection.objects.create(
            ref="destaques",
            name="Destaques",
        )
        assert collection.ref == "destaques"
        assert collection.is_active is True

    def test_hierarchy(self, db):
        parent = Collection.objects.create(ref="breads", name="Breads")
        child = Collection.objects.create(ref="sweet-breads", name="Sweet Breads", parent=parent)

        assert child.parent == parent
        assert child.depth == 1
        assert parent.depth == 0

    def test_full_path(self, db):
        parent = Collection.objects.create(ref="breads", name="Breads")
        child = Collection.objects.create(ref="sweet-breads", name="Sweet Breads", parent=parent)

        assert parent.full_path == "Breads"
        assert child.full_path == "Breads > Sweet Breads"

    def test_is_valid(self, db):
        from datetime import timedelta

        from django.utils import timezone

        today = timezone.now().date()
        coll = Collection.objects.create(
            ref="natal",
            name="Christmas",
            valid_from=today - timedelta(days=1),
            valid_until=today + timedelta(days=1),
        )
        assert coll.is_valid() is True

        coll.valid_from = today + timedelta(days=1)
        assert coll.is_valid() is False


class TestCollectionItem:
    def test_create_item(self, db):
        collection = Collection.objects.create(ref="test", name="Test")
        product = Product.objects.create(sku="PROD", name="Product")

        item = CollectionItem.objects.create(
            collection=collection,
            product=product,
            is_primary=True,
        )
        assert item.is_primary is True
        assert collection.items.count() == 1

    def test_single_primary(self, db):
        col1 = Collection.objects.create(ref="col1", name="Col 1")
        col2 = Collection.objects.create(ref="col2", name="Col 2")
        product = Product.objects.create(sku="PROD", name="Product")

        item1 = CollectionItem.objects.create(
            collection=col1,
            product=product,
            is_primary=True,
        )
        assert item1.is_primary is True

        item2 = CollectionItem.objects.create(
            collection=col2,
            product=product,
            is_primary=True,
        )
        item1.refresh_from_db()

        assert item2.is_primary is True
        assert item1.is_primary is False
