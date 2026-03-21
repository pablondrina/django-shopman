"""
Tests for stock module.

Covers:
- StockIssueResolver
- Stock protocols
"""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from shopman.stock.resolvers import StockIssueResolver
from shopman.ordering.exceptions import IssueResolveError
from shopman.ordering.models import Channel, Session


class StockIssueResolverTests(TestCase):
    """Tests for StockIssueResolver."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(
            ref="stock-test",
            name="Stock Test",
            pricing_policy="external",
            edit_policy="open",
            config={},
        )
        self.session = Session.objects.create(
            session_key="STOCK-RESOLVER-SESSION",
            channel=self.channel,
            state="open",
            rev=5,
            items=[
                {"line_id": "L1", "sku": "PROD-001", "qty": 10, "unit_price_q": 1000, "meta": {}},
            ],
        )
        self.resolver = StockIssueResolver()

    def test_resolver_source_is_stock(self) -> None:
        self.assertEqual(self.resolver.source, "stock")

    def test_resolve_applies_ops(self) -> None:
        issue = {
            "id": "ISS-001",
            "source": "stock",
            "code": "insufficient_stock",
            "context": {
                "actions": [
                    {
                        "id": "ACT-ADJUST",
                        "label": "Adjust quantity",
                        "rev": 5,
                        "ops": [
                            {"op": "set_qty", "line_id": "L1", "qty": 5},
                        ],
                    }
                ]
            },
        }

        self.resolver.resolve(
            session=self.session,
            issue=issue,
            action_id="ACT-ADJUST",
            ctx={},
        )

        self.session.refresh_from_db()
        self.assertEqual(self.session.items[0]["qty"], Decimal("5"))

    def test_resolve_action_not_found_raises_error(self) -> None:
        issue = {
            "id": "ISS-001",
            "source": "stock",
            "code": "insufficient_stock",
            "context": {
                "actions": [
                    {"id": "ACT-OTHER", "ops": []},
                ]
            },
        }

        with self.assertRaises(IssueResolveError) as ctx:
            self.resolver.resolve(
                session=self.session,
                issue=issue,
                action_id="NONEXISTENT",
                ctx={},
            )

        self.assertEqual(ctx.exception.code, "action_not_found")

    def test_resolve_stale_action_raises_error(self) -> None:
        issue = {
            "id": "ISS-001",
            "source": "stock",
            "code": "insufficient_stock",
            "context": {
                "actions": [
                    {
                        "id": "ACT-STALE",
                        "rev": 3,
                        "ops": [{"op": "set_qty", "line_id": "L1", "qty": 1}],
                    }
                ]
            },
        }

        with self.assertRaises(IssueResolveError) as ctx:
            self.resolver.resolve(
                session=self.session,
                issue=issue,
                action_id="ACT-STALE",
                ctx={},
            )

        self.assertEqual(ctx.exception.code, "stale_action")

    def test_resolve_no_ops_raises_error(self) -> None:
        issue = {
            "id": "ISS-001",
            "source": "stock",
            "code": "insufficient_stock",
            "context": {
                "actions": [
                    {
                        "id": "ACT-EMPTY",
                        "rev": 5,
                        "ops": [],
                    }
                ]
            },
        }

        with self.assertRaises(IssueResolveError) as ctx:
            self.resolver.resolve(
                session=self.session,
                issue=issue,
                action_id="ACT-EMPTY",
                ctx={},
            )

        self.assertEqual(ctx.exception.code, "no_ops")

    def test_resolve_with_remove_line_action(self) -> None:
        issue = {
            "id": "ISS-001",
            "source": "stock",
            "code": "out_of_stock",
            "context": {
                "actions": [
                    {
                        "id": "ACT-REMOVE",
                        "label": "Remove item",
                        "rev": 5,
                        "ops": [
                            {"op": "remove_line", "line_id": "L1"},
                        ],
                    }
                ]
            },
        }

        self.resolver.resolve(
            session=self.session,
            issue=issue,
            action_id="ACT-REMOVE",
            ctx={},
        )

        self.session.refresh_from_db()
        self.assertEqual(len(self.session.items), 0)


class StockProtocolTests(TestCase):
    """Tests for stock protocols."""

    def test_stock_backend_protocol_exists(self) -> None:
        from shopman.stock.protocols import StockBackend
        self.assertIsNotNone(StockBackend)

    def test_stock_backend_has_required_methods(self) -> None:
        from shopman.stock.protocols import StockBackend

        methods = [m for m in dir(StockBackend) if not m.startswith("_")]
        self.assertIn("check_availability", methods)
        self.assertIn("create_hold", methods)
        self.assertIn("fulfill_hold", methods)
        self.assertIn("release_hold", methods)
