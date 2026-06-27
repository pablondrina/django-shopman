"""Lot consistency: Batch dates vs Product.shelf_life_days (via SkuValidator).

The check resolves shelf_life through the injected validator (no Offerman import)
— here a fake reporting shelf_life_days=0 (same-day) for every SKU.
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.core.exceptions import ValidationError
from shopman.stockman.adapters.sku_validation import reset_sku_validator
from shopman.stockman.models import Batch
from shopman.stockman.shelflife import batch_window_check

TODAY = dt.date(2026, 6, 27)


@pytest.fixture
def perishable_validator(settings):
    settings.STOCKMAN = {"SKU_VALIDATOR": "shopman.stockman.tests.fakes.PerishableSkuValidator"}
    reset_sku_validator()
    yield
    reset_sku_validator()


@pytest.fixture
def nonperishable_validator(settings):
    settings.STOCKMAN = {"SKU_VALIDATOR": "shopman.stockman.tests.fakes.OrderableSkuValidator"}
    reset_sku_validator()
    yield
    reset_sku_validator()


class TestBatchWindowCheck:
    def test_impossible_dates_is_error(self, perishable_validator):
        error, warning = batch_window_check("X", TODAY, TODAY - dt.timedelta(days=1))
        assert error and warning is None

    def test_exceeds_window_is_warning(self, perishable_validator):
        # shelf_life=0 → max expiry = production day; tomorrow exceeds → warning
        error, warning = batch_window_check("X", TODAY, TODAY + dt.timedelta(days=1))
        assert error is None and warning

    def test_within_window_is_clean(self, perishable_validator):
        error, warning = batch_window_check("X", TODAY, TODAY)
        assert error is None and warning is None

    def test_nonperishable_is_noop(self, nonperishable_validator):
        error, warning = batch_window_check("X", TODAY, TODAY + dt.timedelta(days=999))
        assert error is None and warning is None

    def test_missing_dates_is_noop(self, perishable_validator):
        assert batch_window_check("X", None, TODAY) == (None, None)
        assert batch_window_check("X", TODAY, None) == (None, None)


class TestBatchClean:
    def test_blocks_impossible_dates(self, perishable_validator):
        batch = Batch(ref="L1", sku="X", production_date=TODAY, expiry_date=TODAY - dt.timedelta(days=1))
        with pytest.raises(ValidationError):
            batch.clean()

    def test_allows_over_window_by_default(self, perishable_validator):
        batch = Batch(ref="L2", sku="X", production_date=TODAY, expiry_date=TODAY + dt.timedelta(days=5))
        batch.clean()  # non-strict → warning only, no raise

    def test_strict_blocks_over_window(self, perishable_validator, settings):
        settings.STOCKMAN = {**settings.STOCKMAN, "STRICT_SHELF_LIFE_WINDOW": True}
        batch = Batch(ref="L3", sku="X", production_date=TODAY, expiry_date=TODAY + dt.timedelta(days=5))
        with pytest.raises(ValidationError):
            batch.clean()
