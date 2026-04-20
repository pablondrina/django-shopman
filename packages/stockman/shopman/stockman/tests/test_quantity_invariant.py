"""
Quantity cache invariant tests.

Asserts that after any sequence of stock operations:

    quant._quantity == Σ(moves.delta)

for every Quant touched.

These tests run against the real DB (no mocking).  They are skipped on SQLite
because that backend is used in CI for unit tests; the invariant check itself
is DB-agnostic, but we mark it consistent with WP-GAP-04 / test_concurrency.py.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.conf import settings
from django.db.models import Sum
from django.db.models.functions import Coalesce

from shopman.stockman import StockError, stock
from shopman.stockman.models import Position, PositionKind, Quant

pytestmark = pytest.mark.django_db

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Invariant test suite requires PostgreSQL",
)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def assert_quantity_invariant(*quants: Quant) -> None:
    """
    Assert that every Quant's _quantity equals Σ(moves.delta).

    Refreshes from DB before checking to avoid stale cache.
    """
    for quant in quants:
        quant.refresh_from_db()
        computed = quant.moves.aggregate(
            t=Coalesce(Sum('delta'), Decimal('0'))
        )['t']
        assert quant._quantity == computed, (
            f"Invariant broken for Quant#{quant.pk} [{quant.sku}]: "
            f"_quantity={quant._quantity}, Σ(moves.delta)={computed}, "
            f"delta={computed - quant._quantity}"
        )


def _make_position(ref: str) -> Position:
    pos, _ = Position.objects.get_or_create(
        ref=ref,
        defaults={
            'name': ref.capitalize(),
            'kind': PositionKind.PHYSICAL,
            'is_saleable': True,
        },
    )
    return pos


def _product(sku: str, shelf_life_days=None) -> SimpleNamespace:
    return SimpleNamespace(sku=sku, name=sku, shelf_life_days=shelf_life_days)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

@requires_postgres
class TestQuantityInvariantAfterOperations:
    """
    Verify _quantity == Σ(moves.delta) after 20+ interleaved operations.
    """

    def test_invariant_after_receive_and_issue(self):
        """Basic receive → issue sequence preserves invariant."""
        pos = _make_position('vitrine-inv-1')
        prod = _product('INV-BASIC')
        today = date.today()

        quant = stock.receive(Decimal('100'), prod.sku, pos, reason='Entrada')
        assert_quantity_invariant(quant)

        stock.issue(Decimal('30'), prod.sku, pos, reason='Saída')
        assert_quantity_invariant(quant)

        stock.issue(Decimal('20'), prod.sku, pos, reason='Saída 2')
        assert_quantity_invariant(quant)

        assert quant.refresh_from_db() or quant._quantity == Decimal('50')

    def test_invariant_after_adjust(self):
        """Adjust (positive and negative) preserves invariant."""
        pos = _make_position('vitrine-inv-2')
        prod = _product('INV-ADJUST')

        quant = stock.receive(Decimal('50'), prod.sku, pos, reason='Entrada')
        stock.adjust(prod.sku, pos, Decimal('60'), reason='Ajuste positivo')
        assert_quantity_invariant(quant)

        stock.adjust(prod.sku, pos, Decimal('45'), reason='Ajuste negativo')
        assert_quantity_invariant(quant)

    def test_invariant_after_hold_lifecycle(self):
        """Hold → confirm → fulfill cycle preserves invariant."""
        pos = _make_position('vitrine-inv-3')
        prod = _product('INV-HOLD')
        today = date.today()

        quant = stock.receive(Decimal('80'), prod.sku, pos, reason='Entrada')

        hold = stock.hold(Decimal('20'), prod, today)
        assert_quantity_invariant(quant)

        stock.confirm(hold)
        assert_quantity_invariant(quant)

        stock.fulfill(hold)
        assert_quantity_invariant(quant)

    def test_invariant_after_hold_release(self):
        """Hold → release cycle preserves invariant."""
        pos = _make_position('vitrine-inv-4')
        prod = _product('INV-RELEASE')
        today = date.today()

        quant = stock.receive(Decimal('60'), prod.sku, pos, reason='Entrada')
        hold = stock.hold(Decimal('15'), prod, today)
        assert_quantity_invariant(quant)

        stock.release(hold)
        assert_quantity_invariant(quant)

    def test_invariant_across_multiple_quants(self):
        """Operations on multiple quants all satisfy the invariant."""
        pos_a = _make_position('vitrine-inv-5a')
        pos_b = _make_position('vitrine-inv-5b')
        prod = _product('INV-MULTI')
        today = date.today()

        quant_a = stock.receive(Decimal('100'), prod.sku, pos_a, reason='Entrada A')
        quant_b = stock.receive(Decimal('200'), prod.sku, pos_b, reason='Entrada B')

        stock.issue(Decimal('10'), prod.sku, pos_a, reason='Saída A1')
        stock.issue(Decimal('50'), prod.sku, pos_b, reason='Saída B1')

        assert_quantity_invariant(quant_a, quant_b)

        stock.adjust(prod.sku, pos_a, Decimal('95'), reason='Ajuste A')
        stock.adjust(prod.sku, pos_b, Decimal('140'), reason='Ajuste B')

        assert_quantity_invariant(quant_a, quant_b)

    def test_invariant_twenty_plus_operations(self):
        """At least 20 interleaved operations all preserve the invariant."""
        pos = _make_position('vitrine-inv-6')
        prod = _product('INV-20OPS')
        today = date.today()
        tomorrow = today + timedelta(days=1)

        # 1-3: receive
        quant = stock.receive(Decimal('200'), prod.sku, pos, reason='Entrada 1')
        assert_quantity_invariant(quant)
        stock.receive(Decimal('50'), prod.sku, pos, reason='Entrada 2')
        assert_quantity_invariant(quant)
        stock.receive(Decimal('30'), prod.sku, pos, reason='Entrada 3')
        assert_quantity_invariant(quant)

        # 4-6: hold / confirm / fulfill
        hold1 = stock.hold(Decimal('20'), prod, today)
        assert_quantity_invariant(quant)
        stock.confirm(hold1)
        assert_quantity_invariant(quant)
        stock.fulfill(hold1)
        assert_quantity_invariant(quant)

        # 7-9: hold / confirm / release
        hold2 = stock.hold(Decimal('15'), prod, today)
        assert_quantity_invariant(quant)
        stock.confirm(hold2)
        assert_quantity_invariant(quant)
        stock.release(hold2)
        assert_quantity_invariant(quant)

        # 10-12: issue
        stock.issue(Decimal('5'), prod.sku, pos, reason='Saída 1')
        assert_quantity_invariant(quant)
        stock.issue(Decimal('10'), prod.sku, pos, reason='Saída 2')
        assert_quantity_invariant(quant)
        stock.issue(Decimal('5'), prod.sku, pos, reason='Saída 3')
        assert_quantity_invariant(quant)

        # 13-15: adjust
        stock.adjust(prod.sku, pos, Decimal('220'), reason='Ajuste para cima')
        assert_quantity_invariant(quant)
        stock.adjust(prod.sku, pos, Decimal('215'), reason='Ajuste para baixo')
        assert_quantity_invariant(quant)
        stock.adjust(prod.sku, pos, Decimal('215'), reason='Ajuste noop')
        assert_quantity_invariant(quant)

        # 16-18: another hold cycle
        hold3 = stock.hold(Decimal('10'), prod, today)
        assert_quantity_invariant(quant)
        stock.confirm(hold3)
        assert_quantity_invariant(quant)
        stock.fulfill(hold3)
        assert_quantity_invariant(quant)

        # 19-21: receive + issue + adjust
        stock.receive(Decimal('5'), prod.sku, pos, reason='Entrada final')
        assert_quantity_invariant(quant)
        stock.issue(Decimal('10'), prod.sku, pos, reason='Saída final')
        assert_quantity_invariant(quant)
        stock.adjust(prod.sku, pos, Decimal('200'), reason='Ajuste final')
        assert_quantity_invariant(quant)

        # Sanity: final state
        quant.refresh_from_db()
        assert quant._quantity == Decimal('200')

    def test_guard_blocks_direct_update(self):
        """QuantQuerySet.update(_quantity=X) raises ValueError without escape hatch."""
        pos = _make_position('vitrine-inv-guard')
        prod = _product('INV-GUARD')

        quant = stock.receive(Decimal('50'), prod.sku, pos, reason='Entrada')

        with pytest.raises(ValueError, match='cache de'):
            Quant.objects.filter(pk=quant.pk).update(_quantity=Decimal('999'))

        # With escape hatch: allowed
        Quant.objects.filter(pk=quant.pk).update(
            _quantity=Decimal('999'), _allow_quantity_update=True
        )
        quant.refresh_from_db()
        assert quant._quantity == Decimal('999')

    def test_recalculate_restores_invariant(self):
        """After forced divergence (escape hatch), recalculate() restores invariant."""
        pos = _make_position('vitrine-inv-recalc')
        prod = _product('INV-RECALC')

        quant = stock.receive(Decimal('100'), prod.sku, pos, reason='Entrada')

        # Force divergence using escape hatch
        Quant.objects.filter(pk=quant.pk).update(
            _quantity=Decimal('999'), _allow_quantity_update=True
        )
        quant.refresh_from_db()
        assert quant._quantity == Decimal('999')  # divergent

        quant.recalculate()

        assert_quantity_invariant(quant)
        quant.refresh_from_db()
        assert quant._quantity == Decimal('100')

    def test_clean_raises_on_divergence(self):
        """Quant.clean() raises ValidationError when _quantity diverges."""
        from django.core.exceptions import ValidationError

        pos = _make_position('vitrine-inv-clean')
        prod = _product('INV-CLEAN')

        quant = stock.receive(Decimal('50'), prod.sku, pos, reason='Entrada')

        # Force divergence
        Quant.objects.filter(pk=quant.pk).update(
            _quantity=Decimal('777'), _allow_quantity_update=True
        )
        quant.refresh_from_db()

        with pytest.raises(ValidationError, match='diverge'):
            quant.clean()

    def test_clean_passes_when_consistent(self):
        """Quant.clean() does not raise when _quantity matches moves."""
        pos = _make_position('vitrine-inv-clean2')
        prod = _product('INV-CLEAN2')

        quant = stock.receive(Decimal('30'), prod.sku, pos, reason='Entrada')
        quant.refresh_from_db()

        # Should not raise
        quant.clean()
