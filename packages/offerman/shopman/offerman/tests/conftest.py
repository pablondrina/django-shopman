"""Pytest fixtures for Offerman tests."""

from decimal import Decimal

import pytest
from shopman.offerman.models import Collection, CollectionItem, Listing, ListingItem, Product


@pytest.fixture
def collection(db):
    """Create a test collection."""
    return Collection.objects.create(
        name="Breads",
        ref="breads",
        is_active=True,
    )


@pytest.fixture
def subcollection(db, collection):
    """Create a subcollection."""
    return Collection.objects.create(
        name="Sweet Breads",
        ref="sweet-breads",
        parent=collection,
        is_active=True,
    )


@pytest.fixture
def product(db, collection):
    """Create a test product."""
    prod = Product.objects.create(
        sku="BAGUETE",
        name="Baguete Tradicional",
        unit="un",
        base_price_q=500,  # R$ 5.00
        availability_policy="planned_ok",
        is_sellable=True,
    )
    CollectionItem.objects.create(collection=collection, product=prod, is_primary=True)
    return prod


@pytest.fixture
def hidden_product(db, collection):
    """Create an unpublished product."""
    prod = Product.objects.create(
        sku="HIDDEN-001",
        name="Hidden Product",
        base_price_q=1000,
        is_published=False,
    )
    CollectionItem.objects.create(collection=collection, product=prod)
    return prod


@pytest.fixture
def paused_product(db, collection):
    """Create a paused (non-sellable) product."""
    prod = Product.objects.create(
        sku="PAUSED-001",
        name="Paused Product",
        base_price_q=1000,
        is_sellable=False,
    )
    CollectionItem.objects.create(collection=collection, product=prod)
    return prod


@pytest.fixture
def ingredient(db, collection):
    """Create a non-sellable ingredient."""
    prod = Product.objects.create(
        sku="FLOUR",
        name="Wheat Flour",
        unit="kg",
        base_price_q=300,
        is_sellable=False,
    )
    CollectionItem.objects.create(collection=collection, product=prod)
    return prod


@pytest.fixture
def croissant(db, collection):
    """Create a croissant product."""
    prod = Product.objects.create(
        sku="CROISSANT",
        name="Croissant",
        base_price_q=800,
        shelf_life_days=1,
    )
    CollectionItem.objects.create(collection=collection, product=prod, is_primary=True)
    return prod


@pytest.fixture
def coffee(db, collection):
    """Create a coffee product."""
    prod = Product.objects.create(
        sku="COFFEE",
        name="Espresso Coffee",
        base_price_q=500,
    )
    CollectionItem.objects.create(collection=collection, product=prod, is_primary=True)
    return prod


@pytest.fixture
def combo(db, collection, croissant, coffee):
    """Create a combo/bundle product."""
    from shopman.offerman.models import ProductComponent

    combo = Product.objects.create(
        sku="COMBO-CAFE",
        name="Breakfast Combo",
        base_price_q=1100,
    )
    CollectionItem.objects.create(collection=collection, product=combo, is_primary=True)

    ProductComponent.objects.create(parent=combo, component=croissant, qty=Decimal("1"))
    ProductComponent.objects.create(parent=combo, component=coffee, qty=Decimal("1"))

    return combo


@pytest.fixture
def listing(db):
    """Create a test listing."""
    return Listing.objects.create(
        ref="ifood",
        name="iFood Prices",
        is_active=True,
        priority=10,
    )


@pytest.fixture
def listing_item(db, listing, product):
    """Create a listing item."""
    return ListingItem.objects.create(
        listing=listing,
        product=product,
        price_q=600,
    )


@pytest.fixture
def featured_collection(db, product, croissant):
    """Create a featured collection."""
    coll = Collection.objects.create(
        ref="destaques",
        name="Featured Products",
        is_active=True,
    )
    CollectionItem.objects.create(collection=coll, product=product)
    CollectionItem.objects.create(collection=coll, product=croissant)
    return coll
