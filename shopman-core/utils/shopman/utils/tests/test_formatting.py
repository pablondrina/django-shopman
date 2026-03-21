"""Tests for shopman.utils.formatting."""

from decimal import Decimal

from shopman.utils.formatting import format_quantity


class TestFormatQuantity:
    """format_quantity() with edge cases."""

    def test_none_returns_dash(self):
        assert format_quantity(None) == "-"

    def test_zero(self):
        assert format_quantity(Decimal("0")) == "0.00"

    def test_negative(self):
        assert format_quantity(Decimal("-5.5")) == "-5.50"

    def test_many_decimals_truncates(self):
        assert format_quantity(Decimal("1.23456789"), decimal_places=2) == "1.23"

    def test_many_decimals_with_custom_places(self):
        assert format_quantity(Decimal("1.23456789"), decimal_places=4) == "1.2346"

    def test_zero_decimal_places(self):
        assert format_quantity(Decimal("10.75"), decimal_places=0) == "11"

    def test_large_number(self):
        assert format_quantity(Decimal("999999.99")) == "999999.99"

    def test_very_small_number(self):
        assert format_quantity(Decimal("0.001"), decimal_places=3) == "0.001"

    def test_integer_decimal(self):
        assert format_quantity(Decimal("10")) == "10.00"

    def test_three_decimal_places(self):
        assert format_quantity(Decimal("1.955"), decimal_places=3) == "1.955"
