"""
Pytest fixtures for Stockman tests.

Stockman is catalog-agnostic: tests use plain SKU strings with NoopSkuValidator
(all SKUs are valid). No dependency on offerman or any catalog package.
"""

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from shopman.stockman.models import Position, PositionKind


User = get_user_model()


@pytest.fixture
def user(db):
    """Create a test user."""
    return User.objects.create_user(
        username='testuser',
        password='testpass123'
    )


@pytest.fixture
def product(db):
    """A plain SKU reference for non-perishable stock tests."""
    return SimpleNamespace(sku='PAO-FORMA', name='Pao de Forma', shelflife=None)


@pytest.fixture
def perishable_product(db):
    """A plain SKU reference for perishable stock tests."""
    return SimpleNamespace(sku='CROISSANT', name='Croissant', shelflife=0)


@pytest.fixture
def demand_product(db):
    """A plain SKU reference for demand stock tests."""
    return SimpleNamespace(sku='BOLO-ESPECIAL', name='Bolo Especial', shelflife=3, availability_policy='demand_ok')


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
