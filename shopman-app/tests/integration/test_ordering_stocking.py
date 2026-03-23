"""
Integration tests: Ordering <-> Stocking

Tests the StockmanBackend adapter that connects Ordering's stock module
to Stocking's inventory management.

Covers:
- check_availability
- create_hold
- release_hold
- fulfill_hold
- release_holds_for_reference
"""

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from shopman.inventory.adapters.stockman import StockmanBackend
from shopman.inventory.protocols import AvailabilityResult, HoldResult


pytestmark = pytest.mark.django_db


# =============================================================================
# BACKEND SETUP
# =============================================================================


def get_product_resolver():
    """Create a product resolver function."""
    from shopman.offering.models import Product

    def resolver(sku: str):
        return Product.objects.get(sku=sku)

    return resolver


@pytest.fixture
def backend():
    """Create StockmanBackend instance."""
    return StockmanBackend(product_resolver=get_product_resolver())


# =============================================================================
# CHECK AVAILABILITY
# =============================================================================


class TestCheckAvailability:
    """Tests for StockmanBackend.check_availability()."""

    def test_no_stock_returns_zero_available(self, backend, product, today):
        """Without stock, available_qty should be 0."""
        result = backend.check_availability("PAO-FRANCES", Decimal("10"), today)

        assert isinstance(result, AvailabilityResult)
        assert result.available is False
        assert result.available_qty == Decimal("0")

    def test_with_stock_returns_correct_qty(
        self, backend, product, position_loja, today
    ):
        """With stock, should return correct available quantity."""
        from shopman.stocking import stock

        # Add stock
        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Test stock entry",
        )

        result = backend.check_availability("PAO-FRANCES", Decimal("50"), today)

        assert result.available is True
        assert result.available_qty == Decimal("100")
        assert result.message is None

    def test_insufficient_stock_returns_not_available(
        self, backend, product, position_loja, today
    ):
        """When requesting more than available, should return not available."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("10"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Limited stock",
        )

        result = backend.check_availability("PAO-FRANCES", Decimal("50"), today)

        assert result.available is False
        assert result.available_qty == Decimal("10")
        assert "Disponível: 10" in result.message

    def test_nonexistent_product_returns_not_available(self, backend, today):
        """Nonexistent product should return not available."""
        result = backend.check_availability("NONEXISTENT-SKU", Decimal("1"), today)

        assert result.available is False
        assert result.available_qty == Decimal("0")
        assert "não encontrado" in result.message

    def test_availability_respects_holds(self, backend, product, position_loja, today):
        """Available quantity should subtract active holds."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Stock entry",
        )

        # Create a hold directly
        stock.hold(
            quantity=Decimal("30"),
            product=product,
            target_date=today,
            purpose="test",
            purpose_id="TEST-001",
        )

        result = backend.check_availability("PAO-FRANCES", Decimal("80"), today)

        # 100 - 30 = 70 available
        assert result.available is False
        assert result.available_qty == Decimal("70")


# =============================================================================
# CREATE HOLD
# =============================================================================


class TestCreateHold:
    """Tests for StockmanBackend.create_hold()."""

    def test_create_hold_success(self, backend, product, position_loja, today):
        """Should successfully create hold when stock available."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Stock entry",
        )

        result = backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("10"),
            reference="SESSION-001",
        )

        assert isinstance(result, HoldResult)
        assert result.success is True
        assert result.hold_id is not None
        assert result.hold_id.startswith("hold:")
        assert result.error_code is None

    def test_create_hold_insufficient_stock(self, backend, product, today):
        """Should fail when no stock available."""
        result = backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("10"),
        )

        assert result.success is False
        assert result.error_code is not None

    def test_create_hold_nonexistent_product(self, backend):
        """Should fail for nonexistent product."""
        result = backend.create_hold(
            sku="NONEXISTENT",
            quantity=Decimal("1"),
        )

        assert result.success is False
        assert result.error_code == "product_not_found"

    def test_create_hold_with_expiration(self, backend, product, position_loja, today):
        """Should create hold with expiration time."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Stock entry",
        )

        expires = timezone.now() + timedelta(minutes=30)

        result = backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("10"),
            expires_at=expires,
        )

        assert result.success is True
        # Hold was created successfully with expiration
        assert result.hold_id is not None

    def test_create_hold_reduces_availability(
        self, backend, product, position_loja, today
    ):
        """Creating hold should reduce available quantity."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Stock entry",
        )

        # Check initial availability
        initial = backend.check_availability("PAO-FRANCES", Decimal("100"), today)
        assert initial.available_qty == Decimal("100")

        # Create hold
        backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("30"),
        )

        # Check availability again
        after = backend.check_availability("PAO-FRANCES", Decimal("100"), today)
        assert after.available_qty == Decimal("70")


# =============================================================================
# RELEASE HOLD
# =============================================================================


class TestReleaseHold:
    """Tests for StockmanBackend.release_hold()."""

    def test_release_hold_success(self, backend, product, position_loja, today):
        """Should release hold and restore availability."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Stock entry",
        )

        # Create hold
        result = backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("30"),
        )
        hold_id = result.hold_id

        # Verify availability reduced
        check1 = backend.check_availability("PAO-FRANCES", Decimal("100"), today)
        assert check1.available_qty == Decimal("70")

        # Release hold
        backend.release_hold(hold_id)

        # Verify availability restored
        check2 = backend.check_availability("PAO-FRANCES", Decimal("100"), today)
        assert check2.available_qty == Decimal("100")

    def test_release_nonexistent_hold_is_safe(self, backend):
        """Releasing nonexistent hold should not raise."""
        # Should not raise
        backend.release_hold("hold:999999")

    def test_release_already_released_is_safe(
        self, backend, product, position_loja, today
    ):
        """Releasing already released hold should not raise."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Stock entry",
        )

        result = backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("10"),
        )

        # Release twice - should not raise
        backend.release_hold(result.hold_id)
        backend.release_hold(result.hold_id)


# =============================================================================
# FULFILL HOLD
# =============================================================================


class TestFulfillHold:
    """Tests for StockmanBackend.fulfill_hold()."""

    def test_fulfill_hold_removes_stock(self, backend, product, position_loja, today):
        """Fulfilling hold should remove stock permanently."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Stock entry",
        )

        # Create and fulfill hold
        result = backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("30"),
        )

        backend.fulfill_hold(result.hold_id, reference="ORDER-001")

        # Stock should be reduced permanently (not just held)
        # Total stock is now 70 (100 - 30 fulfilled)
        check = backend.check_availability("PAO-FRANCES", Decimal("100"), today)
        assert check.available_qty == Decimal("70")

    def test_fulfill_nonexistent_hold_raises(self, backend):
        """Fulfilling nonexistent hold should raise StockError."""
        from shopman.stocking.exceptions import StockError

        with pytest.raises(StockError):
            backend.fulfill_hold("hold:999999")


# =============================================================================
# RELEASE HOLDS FOR REFERENCE
# =============================================================================


class TestReleaseHoldsForReference:
    """Tests for StockmanBackend.release_holds_for_reference()."""

    def test_release_multiple_holds_by_reference(
        self, backend, product, position_loja, today
    ):
        """Should release all holds with same reference."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Stock entry",
        )

        # Create multiple holds with same reference
        backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("10"),
            reference="SESSION-XYZ",
        )
        backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("20"),
            reference="SESSION-XYZ",
        )

        # Verify availability reduced
        check1 = backend.check_availability("PAO-FRANCES", Decimal("100"), today)
        assert check1.available_qty == Decimal("70")  # 100 - 10 - 20

        # Release all holds for reference
        count = backend.release_holds_for_reference("SESSION-XYZ")

        assert count == 2

        # Verify availability restored
        check2 = backend.check_availability("PAO-FRANCES", Decimal("100"), today)
        assert check2.available_qty == Decimal("100")

    def test_release_reference_does_not_affect_others(
        self, backend, product, position_loja, today
    ):
        """Should only release holds with matching reference."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Stock entry",
        )

        # Create holds with different references
        backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("10"),
            reference="SESSION-A",
        )
        backend.create_hold(
            sku="PAO-FRANCES",
            quantity=Decimal("20"),
            reference="SESSION-B",
        )

        # Release only SESSION-A
        count = backend.release_holds_for_reference("SESSION-A")

        assert count == 1

        # SESSION-B hold should still be active
        check = backend.check_availability("PAO-FRANCES", Decimal("100"), today)
        assert check.available_qty == Decimal("80")  # 100 - 20 (SESSION-B still held)


# =============================================================================
# PROTOCOL COMPLIANCE
# =============================================================================


class TestProtocolCompliance:
    """Tests that StockmanBackend implements StockBackend protocol."""

    def test_implements_stock_backend_protocol(self, backend):
        """Should implement all StockBackend methods."""
        from shopman.inventory.protocols import StockBackend

        assert isinstance(backend, StockBackend)

    def test_has_required_methods(self, backend):
        """Should have all required protocol methods."""
        assert hasattr(backend, "check_availability")
        assert hasattr(backend, "create_hold")
        assert hasattr(backend, "release_hold")
        assert hasattr(backend, "fulfill_hold")
        assert hasattr(backend, "get_alternatives")
        assert hasattr(backend, "release_holds_for_reference")

    def test_return_types_match_protocol(self, backend, product, position_loja, today):
        """Return types should match protocol definitions."""
        from shopman.stocking import stock

        stock.receive(
            quantity=Decimal("100"),
            sku="PAO-FRANCES",
            position=position_loja,
            target_date=today,
            reason="Test",
        )

        # check_availability returns AvailabilityResult
        avail = backend.check_availability("PAO-FRANCES", Decimal("10"), today)
        assert isinstance(avail, AvailabilityResult)

        # create_hold returns HoldResult
        hold_result = backend.create_hold("PAO-FRANCES", Decimal("10"))
        assert isinstance(hold_result, HoldResult)

        # get_alternatives returns list
        alts = backend.get_alternatives("PAO-FRANCES", Decimal("10"))
        assert isinstance(alts, list)
