"""
Tests for Hold.actor field and actor params on lifecycle methods.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model

from shopman.stockman import stock
from shopman.stockman.models import Hold, Position, PositionKind

pytestmark = pytest.mark.django_db

User = get_user_model()


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def op(db):
    return User.objects.create_user(username='operador', password='x')


@pytest.fixture
def pos(db):
    p, _ = Position.objects.get_or_create(
        ref='cb-vitrine',
        defaults={'name': 'Vitrine CB', 'kind': PositionKind.PHYSICAL, 'is_saleable': True},
    )
    return p


@pytest.fixture
def prod():
    from types import SimpleNamespace
    return SimpleNamespace(sku='CB-PAO', name='Pao CB', shelf_life_days=None)


@pytest.fixture
def today():
    return date.today()


# ── hold() actor ────────────────────────────────────────────────────────

class TestHoldActor:
    def test_hold_stores_actor(self, prod, pos, today, op):
        stock.receive(Decimal('10'), prod.sku, pos, reason='Entrada')
        hold_id = stock.hold(Decimal('3'), prod, today, actor=op)

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.actor == op

    def test_hold_actor_none_by_default(self, prod, pos, today):
        stock.receive(Decimal('10'), prod.sku, pos, reason='Entrada')
        hold_id = stock.hold(Decimal('3'), prod, today)

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.actor is None

    def test_hold_demand_stores_actor(self, prod, today, op):
        """demand_ok policy: actor also stored on demand hold."""
        from types import SimpleNamespace
        demand_prod = SimpleNamespace(
            sku='CB-DEMAND', name='Demand CB',
            shelf_life_days=None, availability_policy='demand_ok',
        )
        hold_id = stock.hold(Decimal('5'), demand_prod, today, actor=op)

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.actor == op


# ── confirm() actor ──────────────────────────────────────────────────────────

class TestConfirmActor:
    def test_confirm_without_actor_no_metadata(self, prod, pos, today):
        stock.receive(Decimal('10'), prod.sku, pos, reason='Entrada')
        hold_id = stock.hold(Decimal('3'), prod, today)

        hold = stock.confirm(hold_id)
        assert 'confirmed_by' not in hold.metadata

    def test_confirm_with_actor_stores_in_metadata(self, prod, pos, today, op):
        stock.receive(Decimal('10'), prod.sku, pos, reason='Entrada')
        hold_id = stock.hold(Decimal('3'), prod, today)

        hold = stock.confirm(hold_id, actor=op)
        assert hold.metadata.get('confirmed_by') == op.pk


# ── release() actor ──────────────────────────────────────────────────────────

class TestReleaseActor:
    def test_release_without_actor_no_metadata(self, prod, pos, today):
        stock.receive(Decimal('10'), prod.sku, pos, reason='Entrada')
        hold_id = stock.hold(Decimal('3'), prod, today)

        hold = stock.release(hold_id)
        assert 'released_by' not in hold.metadata
        assert hold.metadata.get('release_reason') == 'Liberado'

    def test_release_with_actor_stores_in_metadata(self, prod, pos, today, op):
        stock.receive(Decimal('10'), prod.sku, pos, reason='Entrada')
        hold_id = stock.hold(Decimal('3'), prod, today)

        hold = stock.release(hold_id, actor=op)
        assert hold.metadata.get('released_by') == op.pk


# ── fulfill() actor ──────────────────────────────────────────────────────────

class TestFulfillActor:
    def test_fulfill_without_actor_no_metadata(self, prod, pos, today):
        stock.receive(Decimal('10'), prod.sku, pos, reason='Entrada')
        hold_id = stock.hold(Decimal('3'), prod, today)
        stock.confirm(hold_id)

        stock.fulfill(hold_id)
        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert 'fulfilled_by' not in hold.metadata

    def test_fulfill_with_actor_stores_in_metadata(self, prod, pos, today, op):
        stock.receive(Decimal('10'), prod.sku, pos, reason='Entrada')
        hold_id = stock.hold(Decimal('3'), prod, today)
        stock.confirm(hold_id)

        stock.fulfill(hold_id, actor=op)
        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.metadata.get('fulfilled_by') == op.pk

    def test_fulfill_actor_fallback_to_user(self, prod, pos, today, op):
        """When actor not provided, user param is used as fallback."""
        stock.receive(Decimal('10'), prod.sku, pos, reason='Entrada')
        hold_id = stock.hold(Decimal('3'), prod, today)
        stock.confirm(hold_id)

        stock.fulfill(hold_id, user=op)
        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.metadata.get('fulfilled_by') == op.pk
