"""Integration tests for WP-7: stock handler + stock validator.

Tests cover:
- StockHoldHandler processes directives and creates holds via stocking API
- StockHoldHandler is idempotent on retry (skips already-held SKUs)
- StockCheckValidator blocks commit when stock check is missing
- StockCheckValidator blocks commit when stock check is stale
- StockCheckValidator blocks commit when no holds exist
- StockCheckValidator passes when valid stock check with holds exists
- register_stock_extensions registers both in the ordering registry
"""

from decimal import Decimal
from unittest.mock import patch, MagicMock

import pytest
from django.test import TestCase

from shopman.contrib.stock_handler import StockHoldHandler, _SkuRef
from shopman.contrib.stock_validator import StockCheckValidator
from shopman.ordering import registry
from shopman.ordering.exceptions import ValidationError
from shopman.ordering.models import Channel, Directive, Session
from shopman.orchestration import register_stock_extensions


# ---------------------------------------------------------------------------
# StockHoldHandler
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStockHoldHandler(TestCase):

    def setUp(self):
        registry.clear()
        self.handler = StockHoldHandler()
        self.channel = Channel.objects.create(ref="pos", name="PDV")

    def tearDown(self):
        registry.clear()

    def test_handler_has_correct_topic(self):
        assert self.handler.topic == "stock.hold"

    @patch("shopman.contrib.stock_handler.stock")
    def test_handler_creates_holds_for_each_item(self, mock_stock):
        mock_stock.hold.side_effect = ["hold:1", "hold:2"]

        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "order_ref": "ORD-1",
                "channel_ref": "pos",
                "session_key": "S-1",
                "rev": 0,
                "items": [
                    {"sku": "CROISSANT", "qty": "2"},
                    {"sku": "BAGUETTE", "qty": "1"},
                ],
            },
        )

        self.handler.handle(message=directive, ctx={})

        assert mock_stock.hold.call_count == 2

        # Check first call
        args1, kwargs1 = mock_stock.hold.call_args_list[0]
        assert args1[0] == Decimal("2")
        assert args1[1].sku == "CROISSANT"
        assert kwargs1["order_ref"] == "ORD-1"

        # Check second call
        args2, kwargs2 = mock_stock.hold.call_args_list[1]
        assert args2[0] == Decimal("1")
        assert args2[1].sku == "BAGUETTE"

        # Verify directive payload updated with holds
        directive.refresh_from_db()
        holds = directive.payload["result"]["holds"]
        assert len(holds) == 2
        assert holds[0]["hold_id"] == "hold:1"
        assert holds[1]["hold_id"] == "hold:2"

    @patch("shopman.contrib.stock_handler.stock")
    def test_handler_skips_already_held_skus(self, mock_stock):
        """Idempotency: on retry, skips SKUs that already have holds."""
        mock_stock.hold.return_value = "hold:2"

        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "order_ref": "ORD-1",
                "channel_ref": "pos",
                "session_key": "S-1",
                "rev": 0,
                "items": [
                    {"sku": "CROISSANT", "qty": "2"},
                    {"sku": "BAGUETTE", "qty": "1"},
                ],
                "result": {
                    "holds": [
                        {"hold_id": "hold:1", "sku": "CROISSANT", "qty": "2"},
                    ],
                },
            },
        )

        self.handler.handle(message=directive, ctx={})

        # Only BAGUETTE should be held (CROISSANT already done)
        mock_stock.hold.assert_called_once()
        args, kwargs = mock_stock.hold.call_args
        assert args[1].sku == "BAGUETTE"

    @patch("shopman.contrib.stock_handler.stock")
    def test_handler_raises_on_stock_error(self, mock_stock):
        from shopman.stocking.exceptions import StockError
        mock_stock.hold.side_effect = StockError("INSUFFICIENT_AVAILABLE")

        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "order_ref": "ORD-1",
                "channel_ref": "pos",
                "session_key": "S-1",
                "items": [{"sku": "CROISSANT", "qty": "10"}],
            },
        )

        with pytest.raises(StockError):
            self.handler.handle(message=directive, ctx={})

    @patch("shopman.contrib.stock_handler.stock")
    def test_handler_noop_on_empty_items(self, mock_stock):
        directive = Directive.objects.create(
            topic="stock.hold",
            payload={
                "order_ref": "ORD-1",
                "channel_ref": "pos",
                "session_key": "S-1",
                "items": [],
            },
        )

        self.handler.handle(message=directive, ctx={})
        mock_stock.hold.assert_not_called()


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


# ---------------------------------------------------------------------------
# Registration in orchestration
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStockRegistration(TestCase):

    def setUp(self):
        registry.clear()
        # Reset the registration guard so register_stock_extensions() runs fresh
        import shopman.orchestration as orch
        orch._stock_registered = False

    def tearDown(self):
        registry.clear()
        import shopman.orchestration as orch
        orch._stock_registered = False

    def test_register_stock_extensions_adds_handler(self):
        register_stock_extensions()
        handler = registry.get_directive_handler("stock.hold")
        assert handler is not None
        assert handler.topic == "stock.hold"

    def test_register_stock_extensions_adds_validator(self):
        register_stock_extensions()
        validators = registry.get_validators(stage="commit")
        codes = [v.code for v in validators]
        assert "stock_check" in codes

    def test_register_stock_extensions_idempotent(self):
        register_stock_extensions()
        register_stock_extensions()  # Should not raise (duplicate handler)
        assert registry.get_directive_handler("stock.hold") is not None

    def test_setup_channels_registers_stock(self):
        from shopman.orchestration import setup_channels
        setup_channels()
        assert registry.get_directive_handler("stock.hold") is not None
        validators = registry.get_validators(stage="commit")
        codes = [v.code for v in validators]
        assert "stock_check" in codes
