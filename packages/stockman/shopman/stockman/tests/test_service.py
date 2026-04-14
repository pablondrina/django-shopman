"""
Tests for Stock service API.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone
from shopman.stockman import StockError, stock
from shopman.stockman.models import Hold, HoldStatus, Quant

pytestmark = pytest.mark.django_db


class TestStockAvailable:
    """Tests for stock.available()."""

    def test_available_empty_stock(self, product, today):
        """Available returns 0 when no stock exists."""
        assert stock.available(product, today) == Decimal('0')

    def test_available_after_receive(self, product, vitrine, today):
        """Available returns quantity after receive."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada teste')

        assert stock.available(product, today) == Decimal('100')

    def test_available_minus_holds(self, product, vitrine, today):
        """Available = quantity - held."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        stock.hold(Decimal('30'), product, today)

        assert stock.available(product, today) == Decimal('70')

    def test_available_respects_shelflife(self, perishable_product, friday):
        """Perishable product (shelflife=0) only available on production date."""
        stock.plan(Decimal('50'), perishable_product, friday, reason='Produção sexta')

        # Day before: not available
        assert stock.available(perishable_product, friday - timedelta(days=1)) == Decimal('0')

        # On the day: available
        assert stock.available(perishable_product, friday) == Decimal('50')

        # Day after: not available (expired)
        assert stock.available(perishable_product, friday + timedelta(days=1)) == Decimal('0')

    def test_available_extended_shelflife(self, demand_product, friday):
        """Product with shelflife=3 available for 3 days after production."""
        stock.plan(Decimal('10'), demand_product, friday, reason='Produção')

        # On production day
        assert stock.available(demand_product, friday) == Decimal('10')

        # 2 days after
        assert stock.available(demand_product, friday + timedelta(days=2)) == Decimal('10')

        # 4 days after: expired
        assert stock.available(demand_product, friday + timedelta(days=4)) == Decimal('0')


class TestStockReceive:
    """Tests for stock.receive()."""

    def test_receive_creates_quant_and_move(self, product, vitrine):
        """Receive creates Quant and Move."""
        quant = stock.receive(Decimal('50'), product.sku, vitrine, reason='Entrada')

        assert quant._quantity == Decimal('50')
        assert quant.moves.count() == 1
        assert quant.moves.first().delta == Decimal('50')

    def test_receive_updates_existing_quant(self, product, vitrine):
        """Multiple receives update same Quant."""
        stock.receive(Decimal('50'), product.sku, vitrine, reason='Primeira entrada')
        quant = stock.receive(Decimal('30'), product.sku, vitrine, reason='Segunda entrada')

        assert quant._quantity == Decimal('80')
        assert quant.moves.count() == 2

    def test_receive_invalid_quantity(self, product, vitrine):
        """Receive with quantity <= 0 raises error."""
        with pytest.raises(StockError) as exc:
            stock.receive(Decimal('0'), product.sku, vitrine, reason='Zero')

        assert exc.value.code == 'INVALID_QUANTITY'


class TestStockIssue:
    """Tests for stock.issue()."""

    def test_issue_decrements_quantity(self, product, vitrine):
        """Issue decrements Quant quantity."""
        quant = stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        move = stock.issue(Decimal('30'), quant, reason='Saída')

        quant.refresh_from_db()
        assert quant._quantity == Decimal('70')
        assert move.delta == Decimal('-30')

    def test_issue_insufficient_quantity(self, product, vitrine):
        """Issue more than available raises error."""
        quant = stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')

        with pytest.raises(StockError) as exc:
            stock.issue(Decimal('20'), quant, reason='Saída')

        assert exc.value.code == 'INSUFFICIENT_QUANTITY'


class TestStockHold:
    """Tests for stock.hold()."""

    def test_hold_creates_pending_hold(self, product, vitrine, today):
        """Hold creates a PENDING hold."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        hold_id = stock.hold(Decimal('10'), product, today)

        assert hold_id.startswith('hold:')

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.status == HoldStatus.PENDING
        assert hold.quantity == Decimal('10')

    def test_hold_insufficient_available(self, product, today):
        """Hold without stock raises error."""
        with pytest.raises(StockError) as exc:
            stock.hold(Decimal('10'), product, today)

        assert exc.value.code == 'INSUFFICIENT_AVAILABLE'

    def test_hold_demand_ok_creates_demand(self, demand_product, friday):
        """Product with demand_ok policy creates demand hold without stock."""
        hold_id = stock.hold(Decimal('5'), demand_product, friday)

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.is_demand
        assert hold.quant is None

    @override_settings(
        STOCKMAN={"SKU_VALIDATOR": "shopman.stockman.tests.fakes.StockOnlySkuValidator"}
    )
    def test_hold_stock_only_rejects_planned_supply(self, product, producao, tomorrow):
        """stock_only cannot create hold from future planned stock."""
        stock.receive(Decimal('10'), product.sku, producao, target_date=tomorrow, reason='Planejado')

        with pytest.raises(StockError) as exc:
            stock.hold(Decimal('5'), product, tomorrow)

        assert exc.value.code == 'INSUFFICIENT_AVAILABLE'
        assert exc.value.data['available'] == Decimal('0')
        assert exc.value.data['reason_code'] == 'insufficient_supply'

    @override_settings(
        STOCKMAN={"SKU_VALIDATOR": "shopman.stockman.tests.fakes.PausedSkuValidator"}
    )
    def test_hold_paused_offer_rejects_even_with_stock(self, product, vitrine, today):
        """Paused offer cannot be held even if stock physically exists."""
        stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')

        with pytest.raises(StockError) as exc:
            stock.hold(Decimal('5'), product, today)

        assert exc.value.code == 'INSUFFICIENT_AVAILABLE'
        assert exc.value.data['available'] == Decimal('0')
        assert exc.value.data['reason_code'] == 'paused'

    def test_hold_with_expiration(self, product, vitrine, today):
        """Hold with expiration is set."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        expires = timezone.now() + timedelta(minutes=15)

        hold_id = stock.hold(Decimal('10'), product, today, expires_at=expires)

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.expires_at is not None


class TestStockConfirm:
    """Tests for stock.confirm()."""

    def test_confirm_pending_to_confirmed(self, product, vitrine, today):
        """Confirm changes status from PENDING to CONFIRMED."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        hold_id = stock.hold(Decimal('10'), product, today)

        hold = stock.confirm(hold_id)

        assert hold.status == HoldStatus.CONFIRMED

    def test_confirm_invalid_status(self, product, vitrine, today):
        """Confirm non-PENDING hold raises error."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        hold_id = stock.hold(Decimal('10'), product, today)
        stock.confirm(hold_id)  # Now CONFIRMED

        with pytest.raises(StockError) as exc:
            stock.confirm(hold_id)  # Already CONFIRMED

        assert exc.value.code == 'INVALID_STATUS'


class TestStockRelease:
    """Tests for stock.release()."""

    def test_release_pending(self, product, vitrine, today):
        """Release PENDING hold."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        hold_id = stock.hold(Decimal('10'), product, today)

        hold = stock.release(hold_id, reason='Cancelado')

        assert hold.status == HoldStatus.RELEASED
        assert stock.available(product, today) == Decimal('100')  # Freed up

    def test_release_confirmed(self, product, vitrine, today):
        """Release CONFIRMED hold."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        hold_id = stock.hold(Decimal('10'), product, today)
        stock.confirm(hold_id)

        hold = stock.release(hold_id, reason='Cancelado')

        assert hold.status == HoldStatus.RELEASED


class TestStockFulfill:
    """Tests for stock.fulfill()."""

    def test_fulfill_creates_move(self, product, vitrine, today):
        """Fulfill creates exit Move."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        hold_id = stock.hold(Decimal('10'), product, today)
        stock.confirm(hold_id)

        move = stock.fulfill(hold_id)

        assert move.delta == Decimal('-10')

        # Verify hold is fulfilled
        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.status == HoldStatus.FULFILLED

    def test_fulfill_demand_raises_error(self, demand_product, friday):
        """Fulfill demand hold raises error."""
        hold_id = stock.hold(Decimal('5'), demand_product, friday)
        stock.confirm(hold_id)

        with pytest.raises(StockError) as exc:
            stock.fulfill(hold_id)

        assert exc.value.code == 'HOLD_IS_DEMAND'


class TestStockReleaseExpired:
    """Tests for stock.release_expired()."""

    def test_release_expired_holds(self, product, vitrine, today):
        """Expired holds are released."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        # Create hold that expired 1 minute ago
        expires = timezone.now() - timedelta(minutes=1)
        hold_id = stock.hold(Decimal('10'), product, today, expires_at=expires)

        count = stock.release_expired()

        assert count == 1

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.status == HoldStatus.RELEASED


class TestExpiredHoldsIgnored:
    """Tests that expired holds are ignored in availability calculations.

    This is critical: availability must be correct in real-time,
    regardless of whether the cron has run to clean up expired holds.
    """

    def test_available_ignores_expired_holds_before_cron(self, product, vitrine, today):
        """
        Expired holds should not block availability, even before cron runs.
        """
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        expires = timezone.now() - timedelta(minutes=1)
        hold_id = stock.hold(Decimal('10'), product, today, expires_at=expires)

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.status == HoldStatus.PENDING

        available = stock.available(product, today)
        assert available == Decimal('100'), "Expired hold should not block availability"

    def test_hold_is_active_false_when_expired(self, product, vitrine, today):
        """Hold.is_active should return False when expired."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        expires = timezone.now() - timedelta(minutes=1)
        hold_id = stock.hold(Decimal('10'), product, today, expires_at=expires)

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))

        assert hold.status == HoldStatus.PENDING
        assert hold.is_active is False
        assert hold.is_expired is True

    def test_quant_held_ignores_expired_holds(self, product, vitrine, today):
        """Quant.held property should ignore expired holds."""
        quant = stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        valid_expires = timezone.now() + timedelta(minutes=10)
        expired_expires = timezone.now() - timedelta(minutes=1)

        stock.hold(Decimal('20'), product, today, expires_at=valid_expires)
        stock.hold(Decimal('30'), product, today, expires_at=expired_expires)

        quant.refresh_from_db()

        assert quant.held == Decimal('20'), "Expired hold should not be counted in held"
        assert quant.available == Decimal('80'), "Available should be 100 - 20 = 80"

    def test_new_hold_succeeds_when_old_expired(self, product, vitrine, today):
        """Can create new hold when old one expired (before cron)."""
        stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')

        expires = timezone.now() - timedelta(minutes=1)
        old_hold_id = stock.hold(Decimal('10'), product, today, expires_at=expires)

        old_hold = Hold.objects.get(pk=int(old_hold_id.split(':')[1]))
        assert old_hold.status == HoldStatus.PENDING

        new_hold_id = stock.hold(Decimal('10'), product, today)

        assert new_hold_id != old_hold_id
        assert stock.available(product, today) == Decimal('0')


class TestStockHoldRaceCondition:
    """S8: Test race condition in hold — NameError fix."""

    def test_hold_after_stock_exhausted_returns_stock_error(self, product, vitrine, today):
        """Hold when stock is 0 raises StockError, not NameError."""
        stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')
        stock.hold(Decimal('10'), product, today)

        with pytest.raises(StockError) as exc:
            stock.hold(Decimal('1'), product, today)

        assert exc.value.code == 'INSUFFICIENT_AVAILABLE'

    def test_hold_insufficient_reports_current_available(self, product, vitrine, today):
        """StockError includes actual available quantity."""
        stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')
        stock.hold(Decimal('7'), product, today)

        with pytest.raises(StockError) as exc:
            stock.hold(Decimal('5'), product, today)

        assert exc.value.code == 'INSUFFICIENT_AVAILABLE'
        assert exc.value.data['available'] == Decimal('3')


class TestStockAvailableWithPosition:
    """S9: Test available() with position filter."""

    def test_hold_in_position_b_does_not_affect_available_in_position_a(
        self, product, vitrine, producao, today
    ):
        """Hold in position B should not affect available in position A."""
        stock.receive(Decimal('50'), product.sku, vitrine, reason='Entrada vitrine')
        stock.receive(Decimal('50'), product.sku, producao, reason='Entrada producao')

        stock.hold(Decimal('30'), product, today)

        avail_producao = stock.available(product, today, position=producao)
        assert avail_producao == Decimal('50')

    def test_available_all_positions_includes_all_holds(
        self, product, vitrine, producao, today
    ):
        """Available without position sums all quants minus all holds."""
        stock.receive(Decimal('50'), product.sku, vitrine, reason='Entrada vitrine')
        stock.receive(Decimal('50'), product.sku, producao, reason='Entrada producao')

        stock.hold(Decimal('30'), product, today)

        avail_all = stock.available(product, today)
        assert avail_all == Decimal('70')


class TestStockRecalculate:
    """S10: Test recalculate()."""

    def test_recalculate_fixes_inconsistency(self, product, vitrine):
        """Recalculate corrects _quantity when it drifts from moves."""
        quant = stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        Quant.objects.filter(pk=quant.pk).update(_quantity=Decimal('999'))
        quant.refresh_from_db()
        assert quant._quantity == Decimal('999')

        result = quant.recalculate()

        assert result == Decimal('100')
        quant.refresh_from_db()
        assert quant._quantity == Decimal('100')

    def test_recalculate_noop_when_consistent(self, product, vitrine):
        """Recalculate does nothing when _quantity matches moves."""
        quant = stock.receive(Decimal('50'), product.sku, vitrine, reason='Entrada')

        result = quant.recalculate()

        assert result == Decimal('50')
        assert quant._quantity == Decimal('50')


class TestStockAdjustDeltaZero:
    """S11: Test adjust() with delta=0."""

    def test_adjust_delta_zero_returns_none(self, product, vitrine):
        """Adjust with same quantity returns None and creates no Move."""
        quant = stock.receive(Decimal('50'), product.sku, vitrine, reason='Entrada')
        initial_moves = quant.moves.count()

        result = stock.adjust(quant, Decimal('50'), reason='Conferência')

        assert result is None
        assert quant.moves.count() == initial_moves


class TestManagementCommandReleaseExpiredHolds:
    """S12: Test management command release_expired_holds."""

    def test_command_releases_expired(self, product, vitrine, today):
        """Command releases expired holds."""
        from io import StringIO

        from django.core.management import call_command

        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        expires = timezone.now() - timedelta(minutes=1)
        stock.hold(Decimal('10'), product, today, expires_at=expires)

        out = StringIO()
        call_command('release_expired_holds', stdout=out)

        assert '1 bloqueio(s) liberado(s)' in out.getvalue()

    def test_command_dry_run(self, product, vitrine, today):
        """Command --dry-run shows count without releasing."""
        from io import StringIO

        from django.core.management import call_command

        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        expires = timezone.now() - timedelta(minutes=1)
        hold_id = stock.hold(Decimal('10'), product, today, expires_at=expires)

        out = StringIO()
        call_command('release_expired_holds', '--dry-run', stdout=out)

        assert '1 bloqueio(s) seria(m) liberado(s)' in out.getvalue()

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.status == HoldStatus.PENDING


class TestStockPlan:
    """Tests for stock.plan()."""

    def test_plan_creates_future_quant(self, product, friday):
        """Plan creates Quant with target_date."""
        quant = stock.plan(Decimal('50'), product, friday, reason='Produção')

        assert quant.target_date == friday
        assert quant._quantity == Decimal('50')
        assert quant.is_future


class TestStockRealize:
    """Tests for stock.realize()."""

    def test_realize_transfers_planned_to_physical(self, product, vitrine, friday):
        """Realize moves planned stock to physical position."""
        stock.plan(Decimal('50'), product, friday, reason='Produção')

        physical = stock.realize(product, friday, Decimal('50'), vitrine)

        assert physical.target_date is None
        assert physical.position == vitrine
        assert physical._quantity == Decimal('50')

        planned = stock.get_quant(product, target_date=friday)
        assert planned._quantity == Decimal('0')

    def test_realize_adjusts_when_actual_differs(self, product, vitrine, friday):
        """Realize adjusts quantity when actual differs from planned."""
        stock.plan(Decimal('50'), product, friday, reason='Produção')

        physical = stock.realize(product, friday, Decimal('40'), vitrine)

        assert physical._quantity == Decimal('40')

    def test_realize_transfers_holds(self, product, vitrine, friday):
        """Realize migrates active holds from planned to physical quant."""
        stock.plan(Decimal('50'), product, friday, reason='Produção')
        hold_id = stock.hold(Decimal('10'), product, friday)

        physical = stock.realize(product, friday, Decimal('50'), vitrine)

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.quant == physical
        assert hold.quant.target_date is None

    def test_realize_without_plan_raises_error(self, product, vitrine, friday):
        """Realize without existing plan raises QUANT_NOT_FOUND."""
        with pytest.raises(StockError) as exc:
            stock.realize(product, friday, Decimal('50'), vitrine)

        assert exc.value.code == 'QUANT_NOT_FOUND'

    def test_realize_invalid_quantity_raises_error(self, product, vitrine, friday):
        """Realize with quantity <= 0 raises INVALID_QUANTITY."""
        stock.plan(Decimal('50'), product, friday, reason='Produção')

        with pytest.raises(StockError) as exc:
            stock.realize(product, friday, Decimal('0'), vitrine)
        assert exc.value.code == 'INVALID_QUANTITY'

        with pytest.raises(StockError) as exc:
            stock.realize(product, friday, Decimal('-5'), vitrine)
        assert exc.value.code == 'INVALID_QUANTITY'

    def test_realize_full_lifecycle(self, product, vitrine, friday, today):
        """Full lifecycle: plan -> hold -> realize -> fulfill."""
        stock.plan(Decimal('50'), product, friday, reason='Produção')
        hold_id = stock.hold(Decimal('10'), product, friday)
        stock.confirm(hold_id)

        physical = stock.realize(product, friday, Decimal('50'), vitrine)

        move = stock.fulfill(hold_id)
        assert move.delta == Decimal('-10')

        physical.refresh_from_db()
        assert physical._quantity == Decimal('40')


class TestMoveImmutability:
    """Tests for Move immutability."""

    def test_move_cannot_be_updated(self, product, vitrine):
        """Move save with pk raises error."""
        quant = stock.receive(Decimal('50'), product.sku, vitrine, reason='Entrada')
        move = quant.moves.first()

        move.delta = Decimal('100')
        with pytest.raises(ValueError, match="imutáveis"):
            move.save()

    def test_move_cannot_be_deleted(self, product, vitrine):
        """Move delete raises error."""
        quant = stock.receive(Decimal('50'), product.sku, vitrine, reason='Entrada')
        move = quant.moves.first()

        with pytest.raises(ValueError, match="imutáveis"):
            move.delete()
