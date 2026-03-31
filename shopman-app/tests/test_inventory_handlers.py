"""
Tests for stock/handlers module.

Covers:
- StockHoldHandler
- StockCommitHandler
- Stock aggregation
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import Mock

from django.test import TestCase
from django.utils import timezone

from channels.handlers.stock import StockCommitHandler, StockHoldHandler
from channels.protocols import AvailabilityResult, HoldResult
from channels.topics import STOCK_COMMIT, STOCK_HOLD
from shopman.ordering.models import Channel, Directive, Session


class MockStockBackend:
    """Mock stock backend for testing."""

    def __init__(
        self,
        availability: dict[str, AvailabilityResult] | None = None,
        hold_result: HoldResult | None = None,
    ):
        self.availability = availability or {}
        self.hold_result = hold_result or HoldResult(
            success=True,
            hold_id="HOLD-001",
            expires_at=timezone.now() + timedelta(minutes=15),
        )
        self.released_references: list[str] = []
        self.created_holds: list[dict] = []
        self.fulfilled_holds: list[dict] = []

    def check_availability(self, sku: str, quantity: Decimal, target_date=None) -> AvailabilityResult:
        if sku in self.availability:
            return self.availability[sku]
        return AvailabilityResult(available=True, available_qty=quantity)

    def create_hold(self, sku: str, quantity: Decimal, expires_at=None, reference=None, target_date=None, **kwargs) -> HoldResult:
        self.created_holds.append({
            "sku": sku,
            "quantity": quantity,
            "expires_at": expires_at,
            "reference": reference,
        })
        return self.hold_result

    def release_hold(self, hold_id: str) -> None:
        pass

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        self.fulfilled_holds.append({"hold_id": hold_id, "reference": reference})

    def release_holds_for_reference(self, reference: str) -> int:
        self.released_references.append(reference)
        return 0


class StockHoldHandlerTests(TestCase):
    """Tests for StockHoldHandler."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="stock-handler-test",
            name="Stock Handler Test",
            config={},
        )
        self.session = Session.objects.create(
            session_key="STOCK-HOLD-SESSION",
            channel=self.channel,
            state="open",
            rev=1,
            items=[
                {"line_id": "L1", "sku": "PROD-A", "qty": 2, "unit_price_q": 1000},
                {"line_id": "L2", "sku": "PROD-B", "qty": 3, "unit_price_q": 500},
            ],
        )
        self.backend = MockStockBackend()
        self.handler = StockHoldHandler(backend=self.backend)

    def test_handler_has_correct_topic(self) -> None:
        self.assertEqual(self.handler.topic, STOCK_HOLD)

    def test_creates_holds_for_available_stock(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.created_holds), 2)
        self.assertIn("holds", directive.payload)

    def test_releases_previous_holds_before_creating_new(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.assertIn(self.session.session_key, self.backend.released_references)

    def test_aggregates_items_by_sku(self) -> None:
        self.session.update_items([
            {"line_id": "L1", "sku": "SAME-SKU", "qty": 2, "unit_price_q": 100},
            {"line_id": "L2", "sku": "SAME-SKU", "qty": 3, "unit_price_q": 100},
        ])

        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.assertEqual(len(self.backend.created_holds), 1)
        self.assertEqual(self.backend.created_holds[0]["quantity"], Decimal("5"))

    def test_creates_issues_for_insufficient_stock(self) -> None:
        self.backend.availability = {
            "PROD-A": AvailabilityResult(
                available=False,
                available_qty=Decimal("1"),
                message="Apenas 1 unidade disponível",
            ),
        }

        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        issues = self.session.data.get("issues", [])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["source"], "stock")
        self.assertEqual(issues[0]["code"], "stock.insufficient")
        self.assertTrue(issues[0]["blocking"])

    def test_issue_contains_actions(self) -> None:
        self.backend.availability = {
            "PROD-A": AvailabilityResult(
                available=False,
                available_qty=Decimal("1"),
            ),
        }

        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        issue = self.session.data["issues"][0]
        actions = issue["context"]["actions"]

        self.assertEqual(len(actions), 2)
        self.assertIn("Ajustar", actions[0]["label"])
        self.assertEqual(actions[1]["label"], "Remover item")

    def test_skip_when_session_not_found(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": "NONEXISTENT",
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("not found", directive.last_error)
        self.assertEqual(len(self.backend.created_holds), 0)

    def test_skip_when_rev_mismatch(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 999,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("Stale directive", directive.last_error)
        self.assertEqual(len(self.backend.created_holds), 0)

    def test_skip_when_session_not_open(self) -> None:
        self.session.state = "committed"
        self.session.save()

        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.created_holds), 0)

    def test_creates_issue_when_hold_fails(self) -> None:
        self.backend.hold_result = HoldResult(
            success=False,
            error_code="hold_failed",
            message="Falha ao reservar",
        )

        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        issues = self.session.data.get("issues", [])
        self.assertEqual(len(issues), 2)

    def test_stores_check_result_in_session(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        check = self.session.data.get("checks", {}).get("stock", {})
        self.assertIn("result", check)
        self.assertIn("holds", check["result"])

    def test_only_remove_action_when_zero_available(self) -> None:
        self.backend.availability = {
            "PROD-A": AvailabilityResult(
                available=False,
                available_qty=Decimal("0"),
            ),
        }

        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "rev": 1,
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.session.refresh_from_db()
        issue = self.session.data["issues"][0]
        actions = issue["context"]["actions"]

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["label"], "Remover item")


class StockCommitHandlerTests(TestCase):
    """Tests for StockCommitHandler."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="stock-commit-test",
            name="Stock Commit Test",
            config={},
        )
        self.session = Session.objects.create(
            session_key="STOCK-COMMIT-SESSION",
            channel=self.channel,
            state="committed",
            data={
                "checks": {
                    "stock": {
                        "result": {
                            "holds": [
                                {"hold_id": "HOLD-001", "sku": "PROD-A", "qty": 2},
                                {"hold_id": "HOLD-002", "sku": "PROD-B", "qty": 3},
                            ],
                        },
                    },
                },
            },
        )
        self.backend = MockStockBackend()
        self.handler = StockCommitHandler(backend=self.backend)

    def test_handler_has_correct_topic(self) -> None:
        self.assertEqual(self.handler.topic, STOCK_COMMIT)

    def test_fulfills_holds_from_payload(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_COMMIT,
            payload={
                "holds": [
                    {"hold_id": "HOLD-001"},
                    {"hold_id": "HOLD-002"},
                ],
                "order_ref": "ORD-001",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.fulfilled_holds), 2)
        self.assertEqual(self.backend.fulfilled_holds[0]["hold_id"], "HOLD-001")
        self.assertEqual(self.backend.fulfilled_holds[0]["reference"], "ORD-001")

    def test_gets_holds_from_session_when_not_in_payload(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_COMMIT,
            payload={
                "session_key": self.session.session_key,
                "channel_ref": self.channel.ref,
                "order_ref": "ORD-002",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.fulfilled_holds), 2)

    def test_handles_empty_holds(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_COMMIT,
            payload={"holds": []},
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertEqual(len(self.backend.fulfilled_holds), 0)

    def test_handles_session_not_found(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_COMMIT,
            payload={
                "session_key": "NONEXISTENT",
                "channel_ref": self.channel.ref,
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_skips_holds_without_id(self) -> None:
        directive = Directive.objects.create(
            topic=STOCK_COMMIT,
            payload={
                "holds": [
                    {"hold_id": "HOLD-001"},
                    {"sku": "NO-HOLD-ID"},
                ],
            },
        )

        self.handler.handle(message=directive, ctx={})

        self.assertEqual(len(self.backend.fulfilled_holds), 1)


class StockAggregationTests(TestCase):
    """Tests for item aggregation logic."""

    def setUp(self) -> None:
        self.backend = MockStockBackend()
        self.handler = StockHoldHandler(backend=self.backend)

    def test_aggregate_single_item(self) -> None:
        items = [{"line_id": "L1", "sku": "A", "qty": 5}]
        result = self.handler._aggregate_items_by_sku(items)

        self.assertEqual(len(result), 1)
        self.assertEqual(result["A"]["qty"], Decimal("5"))
        self.assertEqual(result["A"]["line_ids"], ["L1"])

    def test_aggregate_multiple_skus(self) -> None:
        items = [
            {"line_id": "L1", "sku": "A", "qty": 2},
            {"line_id": "L2", "sku": "B", "qty": 3},
        ]
        result = self.handler._aggregate_items_by_sku(items)

        self.assertEqual(len(result), 2)
        self.assertEqual(result["A"]["qty"], Decimal("2"))
        self.assertEqual(result["B"]["qty"], Decimal("3"))

    def test_aggregate_same_sku_multiple_lines(self) -> None:
        items = [
            {"line_id": "L1", "sku": "A", "qty": 2},
            {"line_id": "L2", "sku": "A", "qty": 3},
            {"line_id": "L3", "sku": "A", "qty": 1},
        ]
        result = self.handler._aggregate_items_by_sku(items)

        self.assertEqual(len(result), 1)
        self.assertEqual(result["A"]["qty"], Decimal("6"))
        self.assertEqual(result["A"]["line_ids"], ["L1", "L2", "L3"])

    def test_aggregate_mixed_skus(self) -> None:
        items = [
            {"line_id": "L1", "sku": "A", "qty": 2},
            {"line_id": "L2", "sku": "B", "qty": 3},
            {"line_id": "L3", "sku": "A", "qty": 1},
            {"line_id": "L4", "sku": "B", "qty": 2},
        ]
        result = self.handler._aggregate_items_by_sku(items)

        self.assertEqual(result["A"]["qty"], Decimal("3"))
        self.assertEqual(result["B"]["qty"], Decimal("5"))
        self.assertEqual(result["A"]["line_ids"], ["L1", "L3"])
        self.assertEqual(result["B"]["line_ids"], ["L2", "L4"])


class D1PositionFilteringTests(TestCase):
    """Tests for D-1 position filtering via allowed_positions."""

    def test_remote_channel_excludes_d1_position(self):
        """remote() preset has allowed_positions that excludes 'ontem'."""
        from channels.presets import remote

        config = remote()
        allowed = config["stock"]["allowed_positions"]
        self.assertIsNotNone(allowed)
        self.assertNotIn("ontem", allowed)
        self.assertIn("vitrine", allowed)
        self.assertIn("producao", allowed)

    def test_pos_channel_sees_d1_position(self):
        """pos() preset has allowed_positions=None — all positions visible."""
        from channels.presets import pos

        config = pos()
        allowed = config["stock"].get("allowed_positions")
        self.assertIsNone(allowed)

    def test_marketplace_channel_has_no_position_restriction(self):
        """marketplace() preset has allowed_positions=None — default."""
        from channels.presets import marketplace

        config = marketplace()
        allowed = config["stock"].get("allowed_positions")
        self.assertIsNone(allowed)

    def test_stock_config_allowed_positions_default_none(self):
        """StockConfig.allowed_positions defaults to None."""
        from channels.config import ChannelConfig

        stock = ChannelConfig.Stock()
        self.assertIsNone(stock.allowed_positions)

    def test_handler_passes_allowed_positions_to_backend(self):
        """StockHoldHandler passes allowed_positions from channel config."""
        channel = Channel.objects.create(
            ref="d1-test-channel",
            name="D1 Test",
            config={"stock": {"allowed_positions": ["vitrine", "producao"]}},
        )
        session = Session.objects.create(
            session_key="D1-TEST-SESSION",
            channel=channel,
            state="open",
            rev=1,
            items=[{"line_id": "L1", "sku": "PAO", "qty": 1, "unit_price_q": 500}],
        )

        check_calls = []

        class CapturingBackend:
            def check_availability(self, **kwargs):
                check_calls.append(kwargs)
                return AvailabilityResult(available=True, available_qty=Decimal("10"))

            def create_hold(self, **kwargs):
                return HoldResult(
                    success=True,
                    hold_id="HOLD-D1",
                    expires_at=timezone.now() + timedelta(minutes=15),
                )

            def release_holds_for_reference(self, reference):
                return 0

            def get_alternatives(self, sku, qty):
                return []

        handler = StockHoldHandler(backend=CapturingBackend())
        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": session.session_key,
                "channel_ref": channel.ref,
                "rev": 1,
            },
        )
        handler.handle(message=directive, ctx={})

        self.assertEqual(len(check_calls), 1)
        self.assertEqual(check_calls[0]["allowed_positions"], ["vitrine", "producao"])

    def test_handler_omits_allowed_positions_when_none(self):
        """StockHoldHandler does not pass allowed_positions when None (pos channel)."""
        channel = Channel.objects.create(
            ref="pos-d1-test",
            name="POS D1 Test",
            config={"stock": {}},
        )
        session = Session.objects.create(
            session_key="POS-D1-SESSION",
            channel=channel,
            state="open",
            rev=1,
            items=[{"line_id": "L1", "sku": "PAO", "qty": 1, "unit_price_q": 500}],
        )

        check_calls = []

        class CapturingBackend:
            def check_availability(self, **kwargs):
                check_calls.append(kwargs)
                return AvailabilityResult(available=True, available_qty=Decimal("10"))

            def create_hold(self, **kwargs):
                return HoldResult(
                    success=True,
                    hold_id="HOLD-POS",
                    expires_at=timezone.now() + timedelta(minutes=15),
                )

            def release_holds_for_reference(self, reference):
                return 0

            def get_alternatives(self, sku, qty):
                return []

        handler = StockHoldHandler(backend=CapturingBackend())
        directive = Directive.objects.create(
            topic=STOCK_HOLD,
            payload={
                "session_key": session.session_key,
                "channel_ref": channel.ref,
                "rev": 1,
            },
        )
        handler.handle(message=directive, ctx={})

        self.assertEqual(len(check_calls), 1)
        self.assertNotIn("allowed_positions", check_calls[0])
