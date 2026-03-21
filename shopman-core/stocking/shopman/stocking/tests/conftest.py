"""
Pytest fixtures for Stocking tests.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from shopman.offering.models import Product, Collection
from shopman.stocking.models import Position, PositionKind


User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        password='testpass123'
    )


@pytest.fixture
def category(db):
    """Create a test collection."""
    return Collection.objects.create(
        name='Paes',
        slug='paes',
        is_active=True,
    )


@pytest.fixture
def product(db):
    """Create a test product (non-perishable, shelflife=None)."""
    p = Product.objects.create(
        sku='PAO-FORMA',
        name='Pao de Forma',
        unit='un',
        base_price_q=1000,  # R$ 10.00
        is_available=True,
        shelf_life_days=None,  # Non-perishable
        availability_policy='planned_ok',
    )
    p.shelflife = None
    return p


@pytest.fixture
def perishable_product(db):
    """Create a perishable product (shelflife=0, same day only)."""
    p = Product.objects.create(
        sku='CROISSANT',
        name='Croissant',
        unit='un',
        base_price_q=800,  # R$ 8.00
        is_available=True,
        shelf_life_days=0,  # Same day only
        availability_policy='planned_ok',
    )
    p.shelflife = 0
    return p


@pytest.fixture
def demand_product(db):
    """Create a product that accepts demand."""
    p = Product.objects.create(
        sku='BOLO-ESPECIAL',
        name='Bolo Especial',
        unit='un',
        base_price_q=5000,  # R$ 50.00
        is_available=True,
        shelf_life_days=3,  # 3 days
        availability_policy='demand_ok',
    )
    p.shelflife = 3
    return p


@pytest.fixture
def vitrine(db):
    """Get or create vitrine position."""
    position, _ = Position.objects.get_or_create(
        ref='vitrine',
        defaults={
            'name': 'Vitrine Principal',
            'kind': PositionKind.PHYSICAL,
            'is_saleable': True
        }
    )
    return position


@pytest.fixture
def producao(db):
    """Get or create production position."""
    position, _ = Position.objects.get_or_create(
        ref='producao',
        defaults={
            'name': 'Area de Producao',
            'kind': PositionKind.PHYSICAL,
            'is_saleable': False
        }
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


@pytest.fixture
def friday():
    """Return next Friday's date."""
    today = date.today()
    days_until_friday = (4 - today.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7
    return today + timedelta(days=days_until_friday)
