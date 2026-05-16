"""Tests for _favorite_category_from_orders and _history_signals.

Covers the core aggregation logic: SKU tallying from order snapshots,
collection resolution via CollectionItem, and the max-frequency pick.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

pytestmark = pytest.mark.django_db


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def collection_a(db):
    from shopman.offerman.models import Collection
    return Collection.objects.create(ref="pao", name="Pães", is_active=True)


@pytest.fixture
def collection_b(db):
    from shopman.offerman.models import Collection
    return Collection.objects.create(ref="doce", name="Doces", is_active=True)


@pytest.fixture
def product_a1(db, collection_a):
    from shopman.offerman.models import CollectionItem, Product
    p = Product.objects.create(sku="PAO-01", name="Croissant", base_price_q=800)
    CollectionItem.objects.create(collection=collection_a, product=p, is_primary=True)
    return p


@pytest.fixture
def product_a2(db, collection_a):
    from shopman.offerman.models import CollectionItem, Product
    p = Product.objects.create(sku="PAO-02", name="Baguete", base_price_q=500)
    CollectionItem.objects.create(collection=collection_a, product=p, is_primary=True)
    return p


@pytest.fixture
def product_b1(db, collection_b):
    from shopman.offerman.models import CollectionItem, Product
    p = Product.objects.create(sku="DOCE-01", name="Eclair", base_price_q=1200)
    CollectionItem.objects.create(collection=collection_b, product=p, is_primary=True)
    return p


@pytest.fixture
def customer(db):
    from shopman.guestman.models import Customer
    return Customer.objects.create(ref="CUS-FAV-01", first_name="Ana", phone="5543999990011")


def _make_order(customer, skus_qty: list[tuple[str, int]], days_ago: int = 1) -> None:
    """Create an Order for the customer with the given SKU/qty pairs in snapshot."""
    from shopman.orderman.models import Order
    items = [{"sku": sku, "qty": qty, "unit_price_q": 1000} for sku, qty in skus_qty]
    order = Order.objects.create(
        ref=f"ORD-FAV-{Order.objects.count() + 1:04d}",
        channel_ref="nelson",
        handle_type="customer",
        handle_ref=str(customer.uuid),
        snapshot={"items": items},
    )
    # auto_now_add=True ignores the kwarg; backdate via update() to test the 90-day window.
    Order.objects.filter(pk=order.pk).update(
        created_at=timezone.now() - timedelta(days=days_ago)
    )


# ── _favorite_category_from_orders ───────────────────────────────────────────


class TestFavoriteCategoryFromOrders:
    def test_single_collection_wins(self, product_a1, product_b1, customer):
        from shopman.shop.omotenashi.context import _favorite_category_from_orders

        _make_order(customer, [("PAO-01", 2), ("PAO-01", 1)])  # 2 orders for pao
        _make_order(customer, [("DOCE-01", 1)])

        from shopman.orderman.models import Order
        orders = list(
            Order.objects.filter(handle_type="customer", handle_ref=str(customer.uuid))
            .values("created_at", "snapshot")
        )
        result = _favorite_category_from_orders(orders)
        assert result == "pao"

    def test_higher_qty_wins(self, product_a1, product_b1, customer):
        from shopman.orderman.models import Order

        from shopman.shop.omotenashi.context import _favorite_category_from_orders

        _make_order(customer, [("PAO-01", 1)])
        _make_order(customer, [("DOCE-01", 5)])  # higher qty → doce wins

        orders = list(
            Order.objects.filter(handle_type="customer", handle_ref=str(customer.uuid))
            .values("created_at", "snapshot")
        )
        result = _favorite_category_from_orders(orders)
        assert result == "doce"

    def test_two_products_same_collection(self, product_a1, product_a2, product_b1, customer):
        from shopman.orderman.models import Order

        from shopman.shop.omotenashi.context import _favorite_category_from_orders

        # 1 pao-01 + 1 pao-02 = 2 pao total vs 1 doce
        _make_order(customer, [("PAO-01", 1), ("PAO-02", 1), ("DOCE-01", 1)])

        orders = list(
            Order.objects.filter(handle_type="customer", handle_ref=str(customer.uuid))
            .values("created_at", "snapshot")
        )
        result = _favorite_category_from_orders(orders)
        assert result == "pao"

    def test_empty_orders_returns_none(self):
        from shopman.shop.omotenashi.context import _favorite_category_from_orders
        assert _favorite_category_from_orders([]) is None

    def test_orders_with_no_items_returns_none(self, customer):
        from shopman.shop.omotenashi.context import _favorite_category_from_orders

        orders = [{"created_at": timezone.now(), "snapshot": {"items": []}}]
        assert _favorite_category_from_orders(orders) is None

    def test_sku_with_no_collection_ignored(self, customer):
        from shopman.shop.omotenashi.context import _favorite_category_from_orders

        # SKU not linked to any collection
        orders = [{"created_at": timezone.now(), "snapshot": {"items": [{"sku": "GHOST-01", "qty": 5}]}}]
        result = _favorite_category_from_orders(orders)
        assert result is None

    def test_orders_outside_90_days_excluded(self, product_a1, product_b1, customer):
        """_history_signals only passes orders from last 90 days."""
        from shopman.shop.omotenashi.context import _history_signals

        # Order 91 days ago — outside window
        _make_order(customer, [("PAO-01", 10)], days_ago=91)
        # Order 5 days ago with doce
        _make_order(customer, [("DOCE-01", 1)], days_ago=5)

        _, fav = _history_signals(customer)
        assert fav == "doce"

    def test_no_orders_returns_none_none(self, customer):
        from shopman.shop.omotenashi.context import _history_signals
        days, fav = _history_signals(customer)
        assert days is None
        assert fav is None


# ── CatalogProjection integration ────────────────────────────────────────────


class TestCatalogProjectionFavorite:
    def test_favorite_category_ref_present_on_projection(self, product_a1, customer):
        """build_catalog sets favorite_category_ref when request has a customer."""
        from unittest.mock import MagicMock

        from shopman.offerman.models import Listing, ListingItem

        from shopman.storefront.projections.catalog import build_catalog

        # Seed a listing so the product appears
        listing = Listing.objects.create(ref="nelson", name="Nelson", is_active=True)
        ListingItem.objects.create(
            listing=listing, product=product_a1,
            price_q=800, is_published=True, is_sellable=True,
        )
        _make_order(customer, [("PAO-01", 3)], days_ago=2)

        # Build a mock request carrying the customer
        request = MagicMock()
        request.customer = MagicMock()
        request.customer.uuid = customer.uuid
        request.customer.name = customer.name
        request.session = {}

        catalog = build_catalog(channel_ref="nelson", request=request)
        assert catalog.favorite_category_ref == "pao"

    def test_no_orders_favorite_is_none(self, product_a1):
        """Without customer orders, favorite_category_ref is None."""
        from shopman.offerman.models import Listing, ListingItem

        from shopman.storefront.projections.catalog import build_catalog

        listing = Listing.objects.create(ref="nelson2", name="Nelson2", is_active=True)
        ListingItem.objects.create(
            listing=listing, product=product_a1,
            price_q=800, is_published=True, is_sellable=True,
        )

        catalog = build_catalog(channel_ref="nelson2", request=None)
        assert catalog.favorite_category_ref is None
