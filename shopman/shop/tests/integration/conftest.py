"""
Pytest fixtures for integration tests between Shopman apps.

These tests verify the contracts between:
- Orderman <-> Stockman (stock backend)
- Orderman <-> Offerman (pricing backend)
- Craftsman <-> Stockman (production -> stock)
- Craftsman <-> Offerman (recipes -> products)
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

# =============================================================================
# OFFERING FIXTURES (Products)
# =============================================================================


@pytest.fixture
def collection(db):
    """Create a test collection."""
    from shopman.offerman.models import Collection

    return Collection.objects.create(
        name="Padaria",
        ref="padaria",
        is_active=True,
    )


@pytest.fixture
def product(db, collection):
    """Create a sellable product."""
    from shopman.offerman.models import CollectionItem, Product

    p = Product.objects.create(
        sku="PAO-FRANCES",
        name="Pão Francês",
        unit="un",
        base_price_q=80,  # R$ 0.80
        availability_policy="planned_ok",
        is_sellable=True,
    )
    CollectionItem.objects.create(
        collection=collection, product=p, is_primary=True,
    )
    return p


@pytest.fixture
def croissant(db, collection):
    """Create a perishable product (shelf_life_days=0)."""
    from shopman.offerman.models import CollectionItem, Product

    p = Product.objects.create(
        sku="CROISSANT",
        name="Croissant",
        unit="un",
        base_price_q=800,  # R$ 8.00
        shelf_life_days=0,  # Same day only
        availability_policy="planned_ok",
        is_sellable=True,
    )
    CollectionItem.objects.create(
        collection=collection, product=p, is_primary=True,
    )
    return p


@pytest.fixture
def bolo(db, collection):
    """Create a product that accepts demand (for Crafting)."""
    from shopman.offerman.models import CollectionItem, Product

    p = Product.objects.create(
        sku="BOLO-CENOURA",
        name="Bolo de Cenoura",
        unit="un",
        base_price_q=4500,  # R$ 45.00
        shelf_life_days=3,
        availability_policy="demand_ok",
        is_sellable=True,
    )
    CollectionItem.objects.create(
        collection=collection, product=p, is_primary=True,
    )
    return p


@pytest.fixture
def ingredient(db, collection):
    """Create a non-sellable ingredient."""
    from shopman.offerman.models import CollectionItem, Product

    p = Product.objects.create(
        sku="FARINHA",
        name="Farinha de Trigo",
        unit="kg",
        base_price_q=500,  # R$ 5.00/kg
        is_sellable=False,
    )
    CollectionItem.objects.create(
        collection=collection, product=p, is_primary=True,
    )
    return p


@pytest.fixture
def listing(db):
    """Create a test listing for iFood channel."""
    from shopman.offerman.models import Listing

    return Listing.objects.create(
        ref="ifood",
        name="Preços iFood",
        is_active=True,
        priority=10,
    )


@pytest.fixture
def listing_item(db, listing, product):
    """Create listing item for product."""
    from shopman.offerman.models import ListingItem

    return ListingItem.objects.create(
        listing=listing,
        product=product,
        price_q=120,  # R$ 1.20 (50% more for iFood)
    )


# =============================================================================
# STOCKING FIXTURES (Inventory)
# =============================================================================


@pytest.fixture
def position_loja(db):
    """Create store position (saleable)."""
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={
            "name": "Loja Principal",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    return position


@pytest.fixture
def position_producao(db):
    """Create production position (not saleable)."""
    from shopman.stockman.models import Position, PositionKind

    position, _ = Position.objects.get_or_create(
        ref="producao",
        defaults={
            "name": "Área de Produção",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": False,
        },
    )
    return position


@pytest.fixture
def today():
    """Return today's date."""
    return date.today()


@pytest.fixture
def tomorrow():
    """Return tomorrow's date."""
    return date.today() + timedelta(days=1)


# =============================================================================
# ORDERING FIXTURES (Orders)
# =============================================================================


@pytest.fixture
def channel(db):
    """Create a test channel."""
    from shopman.shop.models import Channel

    return Channel.objects.create(
        ref="loja",
        name="Loja Física",
    )


@pytest.fixture
def ifood_channel(db):
    """Create iFood channel."""
    from shopman.shop.models import Channel

    return Channel.objects.create(
        ref="ifood",
        name="iFood",
    )


@pytest.fixture
def session(db, channel):
    """Create a test session."""
    from shopman.orderman.models import Session

    return Session.objects.create(
        session_key="TEST-SESSION-001",
        channel_ref=channel.ref,
        state="open",
        items=[],
    )


# =============================================================================
# CRAFTING FIXTURES (Production)
# =============================================================================


@pytest.fixture
def recipe(db, croissant, ingredient):
    """Create a recipe for croissant production."""
    from shopman.craftsman.models import Recipe, RecipeItem

    recipe = Recipe.objects.create(
        ref="croissant",
        name="Receita Croissant",
        output_ref=croissant.sku,
        batch_size=Decimal("10"),  # Produces 10 units
    )

    # Add ingredient
    RecipeItem.objects.create(
        recipe=recipe,
        input_ref=ingredient.sku,
        quantity=Decimal("0.5"),  # 0.5kg per batch
        unit="kg",
    )

    return recipe


@pytest.fixture
def work_order(db, recipe, today, position_producao, position_loja):
    """Create a work order."""
    from shopman.craftsman.models import WorkOrder

    return WorkOrder.objects.create(
        recipe=recipe,
        output_ref=recipe.output_ref,
        quantity=Decimal("50"),
        status=WorkOrder.Status.PLANNED,
        target_date=today,
        position_ref=position_producao.ref,
    )
