"""
Integration tests: Stock lifecycle operations.

Tests the complete stock flow using Stocking service API
with Offering products: receive, hold, confirm, fulfill, release.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from shopman.stocking import stock, StockError
from shopman.stocking.models import Position, Quant, Hold, HoldStatus


pytestmark = pytest.mark.django_db


class TestStockLifecycle:
    """Tests for the full receive -> hold -> confirm -> fulfill flow."""

    def test_receive_hold_confirm_fulfill(self, product, vitrine, today):
        """Complete lifecycle: receive -> hold -> confirm -> fulfill."""
        # 1. Receive stock
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada inicial')
        assert stock.available(product, today) == Decimal('100')

        # 2. Hold stock
        hold_id = stock.hold(Decimal('10'), product, today)
        assert stock.available(product, today) == Decimal('90')

        # 3. Confirm hold
        hold = stock.confirm(hold_id)
        assert hold.status == HoldStatus.CONFIRMED
        # Confirmed hold still blocks availability
        assert stock.available(product, today) == Decimal('90')

        # 4. Fulfill hold
        move = stock.fulfill(hold_id)
        assert move.delta == Decimal('-10')

        # After fulfillment, hold no longer blocks but quant decreased
        hold_obj = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold_obj.status == HoldStatus.FULFILLED

    def test_receive_multiple_holds_then_fulfill_all(self, product, vitrine, today):
        """Multiple holds from same stock, all fulfilled."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        hold_ids = []
        for i in range(5):
            hid = stock.hold(Decimal('10'), product, today)
            hold_ids.append(hid)

        assert stock.available(product, today) == Decimal('50')

        # Confirm and fulfill all
        for hid in hold_ids:
            stock.confirm(hid)
            stock.fulfill(hid)

        # All fulfilled: quant should have decreased by 50 total
        quant = Quant.objects.filter(sku=product.sku).first()
        assert quant._quantity == Decimal('50')

    def test_perishable_product_lifecycle(self, perishable_product, vitrine, today):
        """Perishable product (shelflife=0) follows same lifecycle."""
        stock.receive(Decimal('50'), perishable_product.sku, vitrine, reason='Producao do dia')

        # Available only on same day
        assert stock.available(perishable_product, today) == Decimal('50')
        assert stock.available(perishable_product, today + timedelta(days=1)) == Decimal('0')

        # Hold and fulfill
        hold_id = stock.hold(Decimal('20'), perishable_product, today)
        assert stock.available(perishable_product, today) == Decimal('30')

        stock.confirm(hold_id)
        stock.fulfill(hold_id)

    def test_demand_product_hold_without_stock(self, demand_product, friday):
        """Demand product can be held without physical stock."""
        # No stock received, but demand_ok policy allows hold
        hold_id = stock.hold(Decimal('5'), demand_product, friday)
        assert hold_id is not None

        hold = Hold.objects.get(pk=int(hold_id.split(':')[1]))
        assert hold.is_demand
        assert hold.quant is None

        # Confirm demand hold
        stock.confirm(hold_id)
        hold.refresh_from_db()
        assert hold.status == HoldStatus.CONFIRMED


class TestMultipleHoldsAndAvailability:
    """Tests for multiple holds reducing availability."""

    def test_sequential_holds_reduce_availability(self, product, vitrine, today):
        """Each hold reduces available quantity."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        stock.hold(Decimal('20'), product, today)
        assert stock.available(product, today) == Decimal('80')

        stock.hold(Decimal('30'), product, today)
        assert stock.available(product, today) == Decimal('50')

        stock.hold(Decimal('50'), product, today)
        assert stock.available(product, today) == Decimal('0')

    def test_holds_from_different_products_independent(
        self, product, perishable_product, vitrine, today
    ):
        """Holds on different products do not affect each other."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada produto A')
        stock.receive(Decimal('50'), perishable_product.sku, vitrine, reason='Entrada produto B')

        stock.hold(Decimal('30'), product, today)

        # Product A: 100 - 30 = 70
        assert stock.available(product, today) == Decimal('70')
        # Product B: unaffected
        assert stock.available(perishable_product, today) == Decimal('50')


class TestHoldReleaseRestoresAvailability:
    """Tests that releasing holds makes stock available again."""

    def test_release_pending_hold(self, product, vitrine, today):
        """Releasing a pending hold restores availability."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        hold_id = stock.hold(Decimal('40'), product, today)
        assert stock.available(product, today) == Decimal('60')

        stock.release(hold_id, reason='Cliente cancelou')
        assert stock.available(product, today) == Decimal('100')

    def test_release_confirmed_hold(self, product, vitrine, today):
        """Releasing a confirmed hold also restores availability."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        hold_id = stock.hold(Decimal('25'), product, today)
        stock.confirm(hold_id)
        assert stock.available(product, today) == Decimal('75')

        stock.release(hold_id, reason='Pedido cancelado')
        assert stock.available(product, today) == Decimal('100')

    def test_release_and_re_hold(self, product, vitrine, today):
        """After releasing, stock can be held again."""
        stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')

        hold_id = stock.hold(Decimal('10'), product, today)
        assert stock.available(product, today) == Decimal('0')

        stock.release(hold_id, reason='Cancelado')
        assert stock.available(product, today) == Decimal('10')

        new_hold_id = stock.hold(Decimal('10'), product, today)
        assert stock.available(product, today) == Decimal('0')
        assert new_hold_id != hold_id


class TestExpiredHoldHandling:
    """Tests that expired holds do not block availability."""

    def test_expired_hold_ignored_in_availability(self, product, vitrine, today):
        """Expired holds do not reduce available quantity."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        # Create hold that's already expired
        expired_at = timezone.now() - timedelta(minutes=1)
        stock.hold(Decimal('50'), product, today, expires_at=expired_at)

        # Available should be full (expired hold ignored)
        assert stock.available(product, today) == Decimal('100')

    def test_new_hold_succeeds_after_expiry(self, product, vitrine, today):
        """Can create a new hold after a previous one expired."""
        stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')

        # First hold takes all, but expires
        expired_at = timezone.now() - timedelta(minutes=1)
        stock.hold(Decimal('10'), product, today, expires_at=expired_at)

        # New hold should succeed since the old one is expired
        new_hold_id = stock.hold(Decimal('10'), product, today)
        assert new_hold_id is not None

    def test_mix_of_valid_and_expired_holds(self, product, vitrine, today):
        """Only valid holds reduce availability; expired ones are ignored."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        valid_expires = timezone.now() + timedelta(minutes=30)
        expired_expires = timezone.now() - timedelta(minutes=5)

        # Valid hold: 20
        stock.hold(Decimal('20'), product, today, expires_at=valid_expires)
        # Expired hold: 30 (should be ignored)
        stock.hold(Decimal('30'), product, today, expires_at=expired_expires)

        # Available = 100 - 20 = 80 (expired hold ignored)
        assert stock.available(product, today) == Decimal('80')


class TestConcurrentHoldScenarios:
    """Tests for holds until stock is exhausted, then error."""

    def test_holds_until_exhausted(self, product, vitrine, today):
        """Multiple holds until stock is fully held."""
        stock.receive(Decimal('5'), product.sku, vitrine, reason='Producao limitada')

        hold_ids = []
        for i in range(5):
            hid = stock.hold(Decimal('1'), product, today)
            hold_ids.append(hid)

        assert stock.available(product, today) == Decimal('0')

        # Next hold should fail
        with pytest.raises(StockError) as exc:
            stock.hold(Decimal('1'), product, today)

        assert exc.value.code == 'INSUFFICIENT_AVAILABLE'

    def test_cannot_hold_more_than_available(self, product, vitrine, today):
        """Cannot hold more than currently available."""
        stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')
        stock.hold(Decimal('7'), product, today)

        # Only 3 left, requesting 5
        with pytest.raises(StockError) as exc:
            stock.hold(Decimal('5'), product, today)

        assert exc.value.code == 'INSUFFICIENT_AVAILABLE'
        assert exc.value.data['available'] == Decimal('3')

    def test_many_holds_and_releases(self, product, vitrine, today):
        """Create and release many holds, verify consistency."""
        stock.receive(Decimal('1000'), product.sku, vitrine, reason='Grande entrada')

        hold_ids = []
        # Create 100 holds of 10 units each
        for i in range(100):
            hid = stock.hold(Decimal('10'), product, today)
            hold_ids.append(hid)

        assert stock.available(product, today) == Decimal('0')

        # Release half
        for hid in hold_ids[:50]:
            stock.release(hid, reason='Cancelado')

        assert stock.available(product, today) == Decimal('500')

        # Confirm the rest
        for hid in hold_ids[50:]:
            stock.confirm(hid)

        # Still 500 held (confirmed holds still block availability)
        assert stock.available(product, today) == Decimal('500')


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_hold_without_stock(self, product, today):
        """Cannot hold when no stock exists."""
        with pytest.raises(StockError) as exc:
            stock.hold(Decimal('1'), product, today)

        assert exc.value.code == 'INSUFFICIENT_AVAILABLE'

    def test_negative_quantity_rejected(self, product, today):
        """Negative quantities are rejected."""
        with pytest.raises(StockError):
            stock.hold(Decimal('-5'), product, today)

    def test_zero_quantity_rejected(self, product, today):
        """Zero quantity is rejected."""
        with pytest.raises(StockError):
            stock.hold(Decimal('0'), product, today)

    def test_double_confirm_raises_error(self, product, vitrine, today):
        """Confirming an already confirmed hold raises error."""
        stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')

        hold_id = stock.hold(Decimal('5'), product, today)
        stock.confirm(hold_id)

        with pytest.raises(StockError) as exc:
            stock.confirm(hold_id)
        assert exc.value.code == 'INVALID_STATUS'

    def test_double_release_raises_error(self, product, vitrine, today):
        """Releasing an already released hold raises error."""
        stock.receive(Decimal('10'), product.sku, vitrine, reason='Entrada')

        hold_id = stock.hold(Decimal('5'), product, today)
        stock.release(hold_id, reason='Primeiro cancelamento')

        with pytest.raises(StockError) as exc:
            stock.release(hold_id, reason='Segundo cancelamento')
        assert exc.value.code == 'INVALID_STATUS'

    def test_receive_zero_raises_error(self, product, vitrine):
        """Receiving zero quantity raises error."""
        with pytest.raises(StockError) as exc:
            stock.receive(Decimal('0'), product.sku, vitrine, reason='Zero')
        assert exc.value.code == 'INVALID_QUANTITY'

    def test_receive_negative_raises_error(self, product, vitrine):
        """Receiving negative quantity raises error."""
        with pytest.raises(StockError) as exc:
            stock.receive(Decimal('-10'), product.sku, vitrine, reason='Negativo')
        assert exc.value.code == 'INVALID_QUANTITY'

    def test_fulfill_without_confirm_raises_error(self, product, vitrine, today):
        """Fulfilling a pending (not confirmed) hold raises error."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')
        hold_id = stock.hold(Decimal('10'), product, today)

        with pytest.raises(StockError) as exc:
            stock.fulfill(hold_id)
        assert exc.value.code == 'INVALID_STATUS'


class TestStressScenarios:
    """Stress tests with many operations."""

    def test_rapid_hold_release_cycles(self, product, vitrine, today):
        """Rapid hold-release cycles maintain consistency."""
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada')

        for i in range(50):
            hold_id = stock.hold(Decimal('10'), product, today)
            stock.release(hold_id, reason=f'Ciclo {i}')

        # All released, full availability restored
        assert stock.available(product, today) == Decimal('100')

    def test_mixed_operations(self, product, vitrine, today):
        """Mixed receive, hold, release, confirm, fulfill operations."""
        # Initial stock
        stock.receive(Decimal('100'), product.sku, vitrine, reason='Entrada 1')

        # Hold 30, confirm 20, release 10
        h1 = stock.hold(Decimal('10'), product, today)
        h2 = stock.hold(Decimal('10'), product, today)
        h3 = stock.hold(Decimal('10'), product, today)

        stock.confirm(h1)
        stock.confirm(h2)
        stock.release(h3, reason='Cancelado')

        # Available: 100 - 10 (confirmed h1) - 10 (confirmed h2) = 80
        assert stock.available(product, today) == Decimal('80')

        # Fulfill h1
        stock.fulfill(h1)

        # Receive more
        stock.receive(Decimal('50'), product.sku, vitrine, reason='Entrada 2')

        # Available: (100 - 10 fulfilled) + 50 - 10 (confirmed h2) = 130
        assert stock.available(product, today) == Decimal('130')
