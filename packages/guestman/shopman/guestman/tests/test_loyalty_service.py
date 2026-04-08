"""
Dedicated tests for LoyaltyService.

Covers:
- enroll: idempotency, inactive customer
- earn_points: happy path, zero/negative points, auto tier upgrade
- redeem_points: happy path, insufficient balance, zero points
- add_stamp: normal, card completion, multiple completions
- get_transactions: ordering, limit
- tier upgrades: bronze→silver→gold→platinum thresholds
- concurrency: select_for_update (conceptual)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from shopman.guestman.contrib.loyalty.models import (
    LoyaltyAccount,
    LoyaltyTier,
    LoyaltyTransaction,
    TransactionType,
)
from shopman.guestman.contrib.loyalty.service import LoyaltyService
from shopman.guestman.exceptions import CustomersError
from shopman.guestman.models import Customer, CustomerGroup


@pytest.fixture
def group(db):
    return CustomerGroup.objects.create(ref="regular", name="Regular", is_default=True, priority=0)


@pytest.fixture
def customer(db, group):
    return Customer.objects.create(
        ref="CUST-LOY-001",
        first_name="Maria",
        last_name="Silva",
        email="maria@example.com",
        phone="+5543999990001",
        group=group,
    )


@pytest.fixture
def customer2(db, group):
    return Customer.objects.create(
        ref="CUST-LOY-002",
        first_name="João",
        last_name="Santos",
        email="joao@example.com",
        phone="+5543999990002",
        group=group,
    )


@pytest.fixture
def enrolled(customer):
    return LoyaltyService.enroll(customer.ref)


# ── Enrollment ──


class TestEnroll:

    def test_enroll_creates_account(self, customer):
        account = LoyaltyService.enroll(customer.ref)

        assert isinstance(account, LoyaltyAccount)
        assert account.customer == customer
        assert account.points_balance == 0
        assert account.lifetime_points == 0
        assert account.tier == LoyaltyTier.BRONZE
        assert account.is_active is True

    def test_enroll_idempotent(self, customer):
        a1 = LoyaltyService.enroll(customer.ref)
        a2 = LoyaltyService.enroll(customer.ref)

        assert a1.pk == a2.pk

    def test_enroll_inactive_customer_raises(self, customer):
        customer.is_active = False
        customer.save()

        with pytest.raises(Customer.DoesNotExist):
            LoyaltyService.enroll(customer.ref)

    def test_enroll_nonexistent_customer_raises(self, db):
        with pytest.raises(Customer.DoesNotExist):
            LoyaltyService.enroll("NONEXISTENT")


# ── Get Account / Balance ──


class TestGetAccount:

    def test_get_account_returns_account(self, enrolled):
        account = LoyaltyService.get_account("CUST-LOY-001")
        assert account is not None
        assert account.pk == enrolled.pk

    def test_get_account_not_enrolled_returns_none(self, customer):
        assert LoyaltyService.get_account(customer.ref) is None

    def test_get_balance_returns_zero_for_not_enrolled(self, customer):
        assert LoyaltyService.get_balance(customer.ref) == 0

    def test_get_balance_returns_current_balance(self, enrolled):
        enrolled.points_balance = 500
        enrolled.save()

        assert LoyaltyService.get_balance("CUST-LOY-001") == 500


# ── Earn Points ──


class TestEarnPoints:

    def test_earn_points_happy_path(self, enrolled):
        tx = LoyaltyService.earn_points(
            "CUST-LOY-001", 100, "Compra", reference="order:123", created_by="system",
        )

        assert isinstance(tx, LoyaltyTransaction)
        assert tx.transaction_type == TransactionType.EARN
        assert tx.points == 100
        assert tx.balance_after == 100
        assert tx.description == "Compra"
        assert tx.reference == "order:123"
        assert tx.created_by == "system"

        enrolled.refresh_from_db()
        assert enrolled.points_balance == 100
        assert enrolled.lifetime_points == 100

    def test_earn_points_accumulates(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 50, "Compra 1")
        LoyaltyService.earn_points("CUST-LOY-001", 75, "Compra 2")

        enrolled.refresh_from_db()
        assert enrolled.points_balance == 125
        assert enrolled.lifetime_points == 125

    def test_earn_zero_points_raises(self, enrolled):
        with pytest.raises(CustomersError) as exc:
            LoyaltyService.earn_points("CUST-LOY-001", 0, "Zero")

        assert exc.value.code == "LOYALTY_INVALID_POINTS"

    def test_earn_negative_points_raises(self, enrolled):
        with pytest.raises(CustomersError) as exc:
            LoyaltyService.earn_points("CUST-LOY-001", -10, "Negative")

        assert exc.value.code == "LOYALTY_INVALID_POINTS"

    def test_earn_not_enrolled_raises(self, customer):
        with pytest.raises(CustomersError) as exc:
            LoyaltyService.earn_points(customer.ref, 100, "Test")

        assert exc.value.code == "LOYALTY_NOT_ENROLLED"

    def test_earn_creates_transaction_record(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 200, "Big purchase")

        txs = LoyaltyTransaction.objects.filter(account=enrolled)
        assert txs.count() == 1
        assert txs.first().points == 200


# ── Redeem Points ──


class TestRedeemPoints:

    def test_redeem_happy_path(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 500, "Earn")

        tx = LoyaltyService.redeem_points(
            "CUST-LOY-001", 200, "Desconto", reference="order:456",
        )

        assert tx.transaction_type == TransactionType.REDEEM
        assert tx.points == -200
        assert tx.balance_after == 300

        enrolled.refresh_from_db()
        assert enrolled.points_balance == 300

    def test_redeem_insufficient_balance_raises(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 50, "Small earn")

        with pytest.raises(CustomersError) as exc:
            LoyaltyService.redeem_points("CUST-LOY-001", 100, "Too much")

        assert exc.value.code == "LOYALTY_INSUFFICIENT_POINTS"

    def test_redeem_exact_balance_succeeds(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 300, "Earn")

        tx = LoyaltyService.redeem_points("CUST-LOY-001", 300, "All points")

        assert tx.balance_after == 0
        enrolled.refresh_from_db()
        assert enrolled.points_balance == 0

    def test_redeem_zero_raises(self, enrolled):
        with pytest.raises(CustomersError):
            LoyaltyService.redeem_points("CUST-LOY-001", 0, "Zero")

    def test_redeem_negative_raises(self, enrolled):
        with pytest.raises(CustomersError):
            LoyaltyService.redeem_points("CUST-LOY-001", -10, "Negative")

    def test_redeem_not_enrolled_raises(self, customer):
        with pytest.raises(CustomersError) as exc:
            LoyaltyService.redeem_points(customer.ref, 100, "Test")

        assert exc.value.code == "LOYALTY_NOT_ENROLLED"

    def test_redeem_does_not_affect_lifetime_points(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 500, "Earn")
        LoyaltyService.redeem_points("CUST-LOY-001", 200, "Redeem")

        enrolled.refresh_from_db()
        assert enrolled.lifetime_points == 500  # Never decreases
        assert enrolled.points_balance == 300


# ── Stamps ──


class TestAddStamp:

    def test_add_stamp_increments(self, enrolled):
        account, completed = LoyaltyService.add_stamp("CUST-LOY-001", description="Visit")

        assert account.stamps_current == 1
        assert completed is False

    def test_stamp_card_completion(self, enrolled):
        """Collecting 10 stamps (default target) completes a card."""
        for i in range(9):
            LoyaltyService.add_stamp("CUST-LOY-001")

        account, completed = LoyaltyService.add_stamp("CUST-LOY-001", description="10th!")

        assert completed is True
        assert account.stamps_current == 0  # Reset
        assert account.stamps_completed == 1

    def test_stamp_card_second_completion(self, enrolled):
        """Complete two cards in a row."""
        for i in range(20):
            LoyaltyService.add_stamp("CUST-LOY-001")

        enrolled.refresh_from_db()
        assert enrolled.stamps_completed == 2
        assert enrolled.stamps_current == 0

    def test_stamp_creates_transaction(self, enrolled):
        LoyaltyService.add_stamp("CUST-LOY-001", reference="visit:42")

        tx = LoyaltyTransaction.objects.filter(
            account=enrolled, transaction_type=TransactionType.STAMP,
        ).first()
        assert tx is not None
        assert tx.points == 1
        assert tx.reference == "visit:42"

    def test_stamp_completion_transaction_description(self, enrolled):
        """Completion stamp has special description."""
        enrolled.stamps_current = 9
        enrolled.save()

        LoyaltyService.add_stamp("CUST-LOY-001")

        tx = LoyaltyTransaction.objects.filter(
            account=enrolled, transaction_type=TransactionType.STAMP,
        ).first()
        assert "Cartela completa" in tx.description

    def test_stamp_not_enrolled_raises(self, customer):
        with pytest.raises(CustomersError) as exc:
            LoyaltyService.add_stamp(customer.ref)

        assert exc.value.code == "LOYALTY_NOT_ENROLLED"

    def test_stamp_custom_target(self, enrolled):
        """Custom stamps_target (e.g., 5)."""
        enrolled.stamps_target = 5
        enrolled.save()

        for i in range(5):
            LoyaltyService.add_stamp("CUST-LOY-001")

        enrolled.refresh_from_db()
        assert enrolled.stamps_completed == 1
        assert enrolled.stamps_current == 0


# ── Tier Upgrades ──


class TestTierUpgrade:

    def test_earn_upgrades_to_silver(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 500, "Big spend")

        enrolled.refresh_from_db()
        assert enrolled.tier == LoyaltyTier.SILVER

    def test_earn_upgrades_to_gold(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 2000, "Very big spend")

        enrolled.refresh_from_db()
        assert enrolled.tier == LoyaltyTier.GOLD

    def test_earn_upgrades_to_platinum(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 5000, "VIP spend")

        enrolled.refresh_from_db()
        assert enrolled.tier == LoyaltyTier.PLATINUM

    def test_incremental_upgrade_bronze_to_silver_to_gold(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 300, "Step 1")
        enrolled.refresh_from_db()
        assert enrolled.tier == LoyaltyTier.BRONZE

        LoyaltyService.earn_points("CUST-LOY-001", 200, "Step 2")  # Total: 500
        enrolled.refresh_from_db()
        assert enrolled.tier == LoyaltyTier.SILVER

        LoyaltyService.earn_points("CUST-LOY-001", 1500, "Step 3")  # Total: 2000
        enrolled.refresh_from_db()
        assert enrolled.tier == LoyaltyTier.GOLD

    def test_tier_never_downgrades_on_redeem(self, enrolled):
        """Redeeming points does not change tier (lifetime_points unchanged)."""
        LoyaltyService.earn_points("CUST-LOY-001", 2000, "Earn gold")
        enrolled.refresh_from_db()
        assert enrolled.tier == LoyaltyTier.GOLD

        LoyaltyService.redeem_points("CUST-LOY-001", 1900, "Big redeem")
        enrolled.refresh_from_db()
        assert enrolled.tier == LoyaltyTier.GOLD  # Still gold
        assert enrolled.points_balance == 100

    def test_below_first_threshold_stays_bronze(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 499, "Almost")

        enrolled.refresh_from_db()
        assert enrolled.tier == LoyaltyTier.BRONZE


# ── Transactions ──


class TestGetTransactions:

    def test_get_transactions_returns_list(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 100, "T1")
        LoyaltyService.earn_points("CUST-LOY-001", 200, "T2")

        txs = LoyaltyService.get_transactions("CUST-LOY-001")
        assert len(txs) == 2

    def test_get_transactions_respects_limit(self, enrolled):
        for i in range(10):
            LoyaltyService.earn_points("CUST-LOY-001", 10, f"T{i}")

        txs = LoyaltyService.get_transactions("CUST-LOY-001", limit=3)
        assert len(txs) == 3

    def test_get_transactions_empty_for_unknown_customer(self, db):
        txs = LoyaltyService.get_transactions("NONEXISTENT")
        assert txs == []

    def test_transactions_ordered_by_created_at_desc(self, enrolled):
        LoyaltyService.earn_points("CUST-LOY-001", 10, "First")
        LoyaltyService.earn_points("CUST-LOY-001", 20, "Second")

        txs = LoyaltyService.get_transactions("CUST-LOY-001")
        # Most recent first (default ordering is -created_at)
        assert txs[0].description == "Second"
        assert txs[1].description == "First"


# ── Model Properties ──


class TestLoyaltyAccountProperties:

    def test_stamps_remaining(self, enrolled):
        enrolled.stamps_current = 7
        enrolled.stamps_target = 10
        assert enrolled.stamps_remaining == 3

    def test_stamps_remaining_zero_when_complete(self, enrolled):
        enrolled.stamps_current = 10
        enrolled.stamps_target = 10
        assert enrolled.stamps_remaining == 0

    def test_stamps_progress_percent(self, enrolled):
        enrolled.stamps_current = 5
        enrolled.stamps_target = 10
        assert enrolled.stamps_progress_percent == 50

    def test_stamps_progress_percent_full(self, enrolled):
        enrolled.stamps_current = 10
        enrolled.stamps_target = 10
        assert enrolled.stamps_progress_percent == 100

    def test_stamps_progress_percent_zero(self, enrolled):
        enrolled.stamps_current = 0
        assert enrolled.stamps_progress_percent == 0

    def test_stamps_progress_percent_zero_target(self, enrolled):
        enrolled.stamps_target = 0
        assert enrolled.stamps_progress_percent == 100
