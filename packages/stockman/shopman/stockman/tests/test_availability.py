"""
Availability tests for Stockman.

Tests that stock.available() correctly computes availability based on
Quant quantities, active holds, expired holds, shelflife, and multiple products.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.test import override_settings
from django.utils import timezone

from shopman.stockman import stock
from shopman.stockman.adapters.offering import reset_sku_validator
from shopman.stockman.services.availability import promise_decision_for_sku
from shopman.stockman.models import Quant, Hold, Position


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _reset_sku_validator_cache():
    reset_sku_validator()
    yield
    reset_sku_validator()


class TestBasicAvailability:
    """Tests for basic availability computation."""

    def test_available_equals_quant_quantity(self, product, vitrine, today):
        """Availability equals the Quant quantity when no holds exist."""
        Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        available = stock.available(product, today)
        assert available == Decimal('50')

    def test_available_zero_without_quant(self, product, today):
        """Availability is zero when no Quant exists."""
        available = stock.available(product, today)
        assert available == Decimal('0')

    def test_available_zero_with_zero_quant(self, product, vitrine, today):
        """Availability is zero when Quant quantity is zero."""
        Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('0'),
        )

        available = stock.available(product, today)
        assert available == Decimal('0')


class TestHoldsReduceAvailability:
    """Tests that pending holds reduce availability."""

    def test_pending_hold_reduces_availability(self, product, vitrine, today):
        """A pending hold reduces available quantity."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('20'),
            status='pending',
            expires_at=timezone.now() + timedelta(hours=1),
        )

        available = stock.available(product, today)
        assert available == Decimal('30')

    def test_confirmed_hold_reduces_availability(self, product, vitrine, today):
        """A confirmed hold also reduces available quantity."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('20'),
            status='confirmed',
            expires_at=None,
        )

        available = stock.available(product, today)
        assert available == Decimal('30')

    def test_multiple_holds_summed(self, product, vitrine, today):
        """Multiple holds are summed to reduce availability."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('100'),
        )

        for i in range(5):
            Hold.objects.create(
                quant=quant,
                sku=product.sku,
                target_date=today,
                quantity=Decimal('15'),
                status='pending',
                expires_at=timezone.now() + timedelta(hours=1),
            )

        # 100 - (5 * 15) = 25
        available = stock.available(product, today)
        assert available == Decimal('25')

    def test_hold_equals_quant_gives_zero(self, product, vitrine, today):
        """Hold equal to quant quantity results in zero availability."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('50'),
            status='pending',
            expires_at=timezone.now() + timedelta(hours=1),
        )

        available = stock.available(product, today)
        assert available == Decimal('0')


class TestExpiredHoldsIgnored:
    """Tests that expired holds do not reduce availability."""

    def test_expired_hold_not_counted(self, product, vitrine, today):
        """An expired hold does not reduce availability."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('20'),
            status='pending',
            expires_at=timezone.now() - timedelta(hours=1),
        )

        available = stock.available(product, today)
        assert available == Decimal('50')

    def test_mix_valid_and_expired_holds(self, product, vitrine, today):
        """Only valid holds reduce availability; expired ones are ignored."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('100'),
        )

        # Valid hold: 20
        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('20'),
            status='pending',
            expires_at=timezone.now() + timedelta(hours=1),
        )

        # Expired hold: 30 (should be ignored)
        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('30'),
            status='pending',
            expires_at=timezone.now() - timedelta(hours=1),
        )

        # Available = 100 - 20 = 80
        available = stock.available(product, today)
        assert available == Decimal('80')


class TestReleasedHoldsIgnored:
    """Tests that released holds do not reduce availability."""

    def test_released_hold_not_counted(self, product, vitrine, today):
        """A released hold does not reduce availability."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('20'),
            status='released',
            expires_at=timezone.now() + timedelta(hours=1),
        )

        available = stock.available(product, today)
        assert available == Decimal('50')

    def test_fulfilled_hold_not_counted(self, product, vitrine, today):
        """A fulfilled hold does not reduce availability (quant already decremented)."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('30'),  # Already decremented by fulfillment
        )

        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('20'),
            status='fulfilled',
            expires_at=None,
        )

        # Available = 30 (fulfilled hold not counted against availability)
        available = stock.available(product, today)
        assert available == Decimal('30')


class TestShelflife:
    """Tests for shelflife affecting availability."""

    def test_shelflife_zero_only_same_day(self, perishable_product, vitrine, today):
        """shelflife=0 product is only available on its production date."""
        yesterday = today - timedelta(days=1)

        # Stock from yesterday
        Quant.objects.create(
            sku=perishable_product.sku,
            position=vitrine,
            target_date=yesterday,
            _quantity=Decimal('100'),
        )

        # Stock from today
        Quant.objects.create(
            sku=perishable_product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('30'),
        )

        # Only today's stock should count
        available = stock.available(perishable_product, today)
        assert available == Decimal('30')

    def test_shelflife_includes_valid_stock(self, demand_product, vitrine, today):
        """Product with shelflife>0 includes stock within validity period."""
        yesterday = today - timedelta(days=1)

        # Stock from yesterday (shelflife=3, so still valid)
        Quant.objects.create(
            sku=demand_product.sku,
            position=vitrine,
            target_date=yesterday,
            _quantity=Decimal('50'),
        )

        # Stock from today
        Quant.objects.create(
            sku=demand_product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('30'),
        )

        available = stock.available(demand_product, today)
        assert available == Decimal('80')

    def test_shelflife_expired_stock_excluded(self, demand_product, vitrine, today):
        """Product with shelflife>0 excludes stock past expiry."""
        old_date = today - timedelta(days=10)  # Well past shelflife=3

        # Stock from 10 days ago (expired, shelflife=3)
        Quant.objects.create(
            sku=demand_product.sku,
            position=vitrine,
            target_date=old_date,
            _quantity=Decimal('100'),
        )

        # Stock from today
        Quant.objects.create(
            sku=demand_product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('20'),
        )

        available = stock.available(demand_product, today)
        assert available == Decimal('20')


class TestMultipleProductsIndependent:
    """Tests that availability is independent per product."""

    def test_different_products_independent(
        self, product, perishable_product, vitrine, today
    ):
        """Availability of different products is independent."""
        Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('30'),
        )

        Quant.objects.create(
            sku=perishable_product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        avail_a = stock.available(product, today)
        avail_b = stock.available(perishable_product, today)

        assert avail_a == Decimal('30')
        assert avail_b == Decimal('50')

    def test_hold_affects_only_target_product(
        self, product, perishable_product, vitrine, today
    ):
        """Hold on one product does not affect another."""
        quant_a = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('30'),
        )

        Quant.objects.create(
            sku=perishable_product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        # Hold only on product A
        Hold.objects.create(
            quant=quant_a,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('20'),
            status='pending',
            expires_at=timezone.now() + timedelta(hours=1),
        )

        # Product A: 30 - 20 = 10
        assert stock.available(product, today) == Decimal('10')
        # Product B: still 50 (unaffected)
        assert stock.available(perishable_product, today) == Decimal('50')


class TestHoldExpiration:
    """Tests for hold expiration edge cases."""

    def test_hold_about_to_expire_still_counts(self, product, vitrine, today):
        """A hold expiring in 1 second still reduces availability."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        # Hold expires in 1 second (still active)
        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('20'),
            status='pending',
            expires_at=timezone.now() + timedelta(seconds=1),
        )

        available = stock.available(product, today)
        assert available == Decimal('30')

    def test_confirmed_hold_no_expiration(self, product, vitrine, today):
        """Confirmed hold without expiration always reduces availability."""
        quant = Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        # Confirmed hold, no expiration
        Hold.objects.create(
            quant=quant,
            sku=product.sku,
            target_date=today,
            quantity=Decimal('20'),
            status='confirmed',
            expires_at=None,
        )

        available = stock.available(product, today)
        assert available == Decimal('30')


class TestFutureDates:
    """Tests for availability on future dates."""

    def test_future_date_no_stock_perishable(self, perishable_product, vitrine, today):
        """Perishable stock planned for today is NOT available 5 days later."""
        future = today + timedelta(days=5)

        # Perishable stock (shelflife=0) planned for today
        Quant.objects.create(
            sku=perishable_product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        # shelflife=0 means same-day only — not valid 5 days later
        available = stock.available(perishable_product, future)
        assert available == Decimal('0')

    def test_future_date_non_perishable_still_available(self, product, vitrine, today):
        """Non-perishable stock planned for today IS available on future dates."""
        future = today + timedelta(days=5)

        Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal('50'),
        )

        # Non-perishable: production from today is still valid in 5 days
        available = stock.available(product, future)
        assert available == Decimal('50')

    def test_planned_stock_available_on_target_date(self, product, friday):
        """Planned stock (via stock.plan) is available on target date."""
        stock.plan(Decimal('50'), product, friday, reason='Producao sexta')

        assert stock.available(product, friday) == Decimal('50')
        assert stock.available(product, friday - timedelta(days=1)) == Decimal('0')


class TestPromiseDecision:
    """Explicit promise decisions expose operational approval and reason."""

    @override_settings(
        STOCKMAN={"SKU_VALIDATOR": "shopman.stockman.tests.fakes.OrderableSkuValidator"}
    )
    def test_promise_decision_approves_when_orderable(self, product, vitrine, today):
        Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal("10"),
        )

        decision = promise_decision_for_sku(product.sku, Decimal("3"), target_date=today)

        assert decision.approved is True
        assert decision.reason_code is None
        assert decision.available_qty == Decimal("10")
        assert decision.available == Decimal("10")
        assert decision.expected == Decimal("10")
        assert decision.planned == Decimal("0")

    @override_settings(
        STOCKMAN={"SKU_VALIDATOR": "shopman.stockman.tests.fakes.OrderableSkuValidator"}
    )
    def test_promise_decision_rejects_when_insufficient(self, product, vitrine, today):
        Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal("2"),
        )

        decision = promise_decision_for_sku(product.sku, Decimal("3"), target_date=today)

        assert decision.approved is False
        assert decision.reason_code == "insufficient_supply"
        assert decision.available_qty == Decimal("2")

    @override_settings(
        STOCKMAN={"SKU_VALIDATOR": "shopman.stockman.tests.fakes.PausedSkuValidator"}
    )
    def test_promise_decision_rejects_non_orderable_offer(self, vitrine, today):
        sku = "ING-001"
        Quant.objects.create(
            sku=sku,
            position=vitrine,
            target_date=today,
            _quantity=Decimal("10"),
        )

        decision = promise_decision_for_sku(sku, Decimal("1"), target_date=today)

        assert decision.approved is False
        assert decision.reason_code == "paused"
        assert decision.available_qty == Decimal("0")

    @override_settings(
        STOCKMAN={"SKU_VALIDATOR": "shopman.stockman.tests.fakes.OrderableSkuValidator"}
    )
    def test_promise_decision_exposes_planned_supply(self, product, tomorrow):
        Quant.objects.create(
            sku=product.sku,
            position=None,
            target_date=tomorrow,
            _quantity=Decimal("8"),
        )

        decision = stock.promise(product.sku, Decimal("6"), target_date=tomorrow)

        assert decision.approved is True
        assert decision.available == Decimal("0")
        assert decision.expected == Decimal("0")
        assert decision.planned == Decimal("8")
        assert decision.available_qty == Decimal("8")

    @override_settings(
        STOCKMAN={"SKU_VALIDATOR": "shopman.stockman.tests.fakes.OrderableSkuValidator"}
    )
    def test_promise_decision_distinguishes_expected_from_planned_supply(
        self, product, producao, tomorrow
    ):
        Quant.objects.create(
            sku=product.sku,
            position=None,
            target_date=tomorrow,
            _quantity=Decimal("20"),
        )
        Quant.objects.create(
            sku=product.sku,
            position=producao,
            target_date=tomorrow,
            batch="started",
            _quantity=Decimal("30"),
        )

        decision = stock.promise(product.sku, Decimal("25"), target_date=tomorrow)

        assert decision.approved is True
        assert decision.available == Decimal("0")
        assert decision.expected == Decimal("30")
        assert decision.planned == Decimal("20")
        assert decision.available_qty == Decimal("50")

    @override_settings(
        STOCKMAN={"SKU_VALIDATOR": "shopman.stockman.tests.fakes.StockOnlySkuValidator"}
    )
    def test_stock_only_policy_ignores_in_process_and_plan_for_promise(self, product, vitrine, tomorrow):
        Quant.objects.create(
            sku=product.sku,
            position=vitrine,
            target_date=tomorrow,
            _quantity=Decimal("5"),
        )
        decision = promise_decision_for_sku(product.sku, Decimal("1"), target_date=tomorrow)
        assert decision.availability_policy == "stock_only"
        assert decision.approved is False
        assert decision.available_qty == Decimal("0")
        assert decision.planned == Decimal("5")

    @override_settings(
        STOCKMAN={"SKU_VALIDATOR": "shopman.stockman.tests.fakes.DemandOkSkuValidator"}
    )
    def test_demand_ok_policy_approves_beyond_current_supply(self, product, today):
        decision = promise_decision_for_sku(product.sku, Decimal("7"), target_date=today)
        assert decision.availability_policy == "demand_ok"
        assert decision.approved is True
        assert decision.available_qty == Decimal("7")
        assert decision.available == Decimal("0")
        assert decision.expected == Decimal("0")
        assert decision.planned == Decimal("0")
