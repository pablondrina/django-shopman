"""Tests for shopman.utils.monetary — canonical monetary rounding."""

from decimal import Decimal

import pytest

from shopman.utils.monetary import monetary_div, monetary_mult


class TestMonetaryMult:
    """monetary_mult: qty * unit_price_q with ROUND_HALF_UP."""

    def test_integer_qty(self):
        assert monetary_mult(Decimal("2"), 500) == 1000

    def test_fractional_qty_rounds_up(self):
        # 2.5 * 333 = 832.5 → 833 (ROUND_HALF_UP)
        assert monetary_mult(Decimal("2.5"), 333) == 833

    def test_fractional_qty_rounds_down(self):
        # 2.4 * 333 = 799.2 → 799
        assert monetary_mult(Decimal("2.4"), 333) == 799

    def test_zero_qty(self):
        assert monetary_mult(Decimal("0"), 1000) == 0

    def test_zero_price(self):
        assert monetary_mult(Decimal("5"), 0) == 0

    def test_large_values(self):
        # 1000 * 99999 = 99_999_000
        assert monetary_mult(Decimal("1000"), 99999) == 99_999_000

    def test_one_centavo(self):
        assert monetary_mult(Decimal("1"), 1) == 1

    def test_typical_bakery_order(self):
        # 3 pães a R$ 1.50 (150 centavos)
        assert monetary_mult(Decimal("3"), 150) == 450

    def test_half_up_not_half_even(self):
        # 0.5 * 1 = 0.5 → 1 (HALF_UP), not 0 (HALF_EVEN/banker's)
        assert monetary_mult(Decimal("0.5"), 1) == 1


class TestMonetaryDiv:
    """monetary_div: total_q / divisor with ROUND_HALF_UP."""

    def test_exact_division(self):
        assert monetary_div(1000, 2) == 500

    def test_remainder_rounds(self):
        # 1000 / 3 = 333.33... → 333
        assert monetary_div(1000, 3) == 333

    def test_zero_total(self):
        assert monetary_div(0, 5) == 0

    def test_divisor_one(self):
        assert monetary_div(1234, 1) == 1234

    def test_divisor_zero_raises(self):
        with pytest.raises(ValueError, match="divisor must be > 0"):
            monetary_div(1000, 0)

    def test_negative_divisor_raises(self):
        with pytest.raises(ValueError, match="divisor must be > 0"):
            monetary_div(1000, -1)

    def test_half_up_not_truncation(self):
        # 999 / 2 = 499.5 → 500 (ROUND_HALF_UP), not 499 (truncation)
        assert monetary_div(999, 2) == 500

    def test_half_up_boundary(self):
        # 1001 / 2 = 500.5 → 501 (ROUND_HALF_UP)
        assert monetary_div(1001, 2) == 501

    def test_rounds_down_below_half(self):
        # 1000 / 3 = 333.33... → 333 (below .5, rounds down)
        assert monetary_div(1000, 3) == 333

    def test_rounds_up_above_half(self):
        # 2000 / 3 = 666.66... → 667 (above .5, rounds up)
        assert monetary_div(2000, 3) == 667
