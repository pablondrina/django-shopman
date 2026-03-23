"""Integration tests for StockCheckValidator.

Tests cover:
- StockCheckValidator blocks commit when stock check is missing
- StockCheckValidator blocks commit when stock check is stale
- StockCheckValidator blocks commit when no holds exist
- StockCheckValidator passes when valid stock check with holds exists
"""

import pytest
from django.test import TestCase

from shopman.stock.validator import StockCheckValidator
from shopman.ordering import registry
from shopman.ordering.exceptions import ValidationError
from shopman.ordering.models import Channel, Session


# ---------------------------------------------------------------------------
# StockCheckValidator
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStockCheckValidator(TestCase):

    def setUp(self):
        registry.clear()
        self.validator = StockCheckValidator()
        self.channel = Channel.objects.create(
            ref="pos",
            name="PDV",
            config={"required_checks_on_commit": ["stock"]},
        )

    def tearDown(self):
        registry.clear()

    def test_validator_has_correct_code_and_stage(self):
        assert self.validator.code == "stock_check"
        assert self.validator.stage == "commit"

    def test_blocks_commit_when_stock_check_missing(self):
        session = Session.objects.create(
            session_key="S-1",
            channel=self.channel,
            items=[{"sku": "CROISSANT", "qty": 2, "unit_price_q": 500, "line_id": "L-1"}],
            data={},
        )

        with pytest.raises(ValidationError, match="missing_stock_check"):
            self.validator.validate(channel=self.channel, session=session, ctx={})

    def test_blocks_commit_when_stock_check_stale(self):
        session = Session.objects.create(
            session_key="S-2",
            channel=self.channel,
            items=[{"sku": "CROISSANT", "qty": 2, "unit_price_q": 500, "line_id": "L-1"}],
            data={
                "checks": {
                    "stock": {
                        "rev": 0,
                        "result": {"holds": [{"hold_id": "hold:1", "sku": "CROISSANT"}]},
                    },
                },
            },
            rev=1,  # Session was modified after check
        )

        with pytest.raises(ValidationError, match="stale_stock_check"):
            self.validator.validate(channel=self.channel, session=session, ctx={})

    def test_blocks_commit_when_no_holds(self):
        session = Session.objects.create(
            session_key="S-3",
            channel=self.channel,
            items=[{"sku": "CROISSANT", "qty": 2, "unit_price_q": 500, "line_id": "L-1"}],
            data={
                "checks": {
                    "stock": {
                        "rev": 0,
                        "result": {"holds": []},
                    },
                },
            },
            rev=0,
        )

        with pytest.raises(ValidationError, match="no_stock_holds"):
            self.validator.validate(channel=self.channel, session=session, ctx={})

    def test_passes_when_valid_stock_check_with_holds(self):
        session = Session.objects.create(
            session_key="S-4",
            channel=self.channel,
            items=[{"sku": "CROISSANT", "qty": 2, "unit_price_q": 500, "line_id": "L-1"}],
            data={
                "checks": {
                    "stock": {
                        "rev": 0,
                        "result": {
                            "holds": [
                                {"hold_id": "hold:1", "sku": "CROISSANT", "qty": "2"},
                            ],
                        },
                    },
                },
            },
            rev=0,
        )

        # Should not raise
        self.validator.validate(channel=self.channel, session=session, ctx={})

    def test_skips_when_stock_not_required(self):
        """Channels without stock in required_checks skip validation."""
        channel_no_stock = Channel.objects.create(
            ref="marketplace",
            name="MP",
            config={"required_checks_on_commit": []},
        )
        session = Session.objects.create(
            session_key="S-5",
            channel=channel_no_stock,
            items=[{"sku": "CROISSANT", "qty": 2, "unit_price_q": 500, "line_id": "L-1"}],
            data={},
        )

        # Should not raise — stock check not required
        self.validator.validate(channel=channel_no_stock, session=session, ctx={})
