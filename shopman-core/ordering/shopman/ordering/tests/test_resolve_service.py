from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from shopman.ordering import registry
from shopman.ordering.contrib.stock.resolvers import StockIssueResolver
from shopman.ordering.exceptions import IssueResolveError
from shopman.ordering.models import Channel, Directive, Session
from shopman.ordering.services import ResolveService


class ResolveServiceTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        registry.clear()
        registry.register_issue_resolver(StockIssueResolver())

        # Register mock stock check for ModifyService
        class _MockStockCheck:
            code = "stock"
            topic = "stock.hold"
            def validate(self, *, channel, session, ctx):
                pass
        registry.register_check(_MockStockCheck())

        self.channel = Channel.objects.create(
            ref="pos",
            name="POS",
            config={
                "rules": {"checks": ["stock"]},
            },
        )

    def tearDown(self) -> None:
        registry.clear()
        super().tearDown()

    def _session_with_issue(self) -> Session:
        issue = {
            "id": "ISS-1",
            "source": "stock",
            "code": "stock.insufficient",
            "blocking": True,
            "message": "Disponível: 2",
            "context": {
                "line_id": "L-1",
                "sku": "SKU",
                "requested_qty": 5.0,
                "available_qty": 2.0,
                "actions": [
                    {
                        "id": "ACT-SET",
                        "label": "Ajustar para 2",
                        "rev": 0,
                        "ops": [{"op": "set_qty", "line_id": "L-1", "qty": 2}],
                    },
                    {
                        "id": "ACT-REMOVE",
                        "label": "Remover",
                        "rev": 0,
                        "ops": [{"op": "remove_line", "line_id": "L-1"}],
                    },
                ],
            },
        }

        return Session.objects.create(
            session_key="SESS-RESOLVE",
            channel=self.channel,
            state="open",
            pricing_policy=self.channel.pricing_policy,
            edit_policy="open",
            rev=0,
            items=[
                {"line_id": "L-1", "sku": "SKU", "qty": 5, "unit_price_q": 1000, "meta": {}},
                {"line_id": "L-2", "sku": "OTHER", "qty": 1, "unit_price_q": 500, "meta": {}},
            ],
            data={"checks": {"stock": {"rev": 0}}, "issues": [issue]},
        )

    def test_resolve_action_updates_only_target_line(self) -> None:
        session = self._session_with_issue()

        ResolveService.resolve(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            issue_id="ISS-1",
            action_id="ACT-SET",
            ctx={"actor": "test"},
        )

        session.refresh_from_db()
        self.assertEqual(session.items[0]["qty"], Decimal("2"))
        self.assertEqual(session.items[1]["qty"], Decimal("1"))
        self.assertEqual(session.data["issues"], [])
        self.assertEqual(session.data["checks"], {})

    def test_resolve_enqueues_new_stock_check(self) -> None:
        session = self._session_with_issue()

        ResolveService.resolve(
            session_key=session.session_key,
            channel_ref=self.channel.ref,
            issue_id="ISS-1",
            action_id="ACT-SET",
            ctx={"actor": "test"},
        )

        directive = Directive.objects.filter(topic="stock.hold").order_by("-id").first()
        self.assertIsNotNone(directive)
        self.assertEqual(directive.payload["session_key"], session.session_key)

    def test_resolve_respects_locked_sessions(self) -> None:
        session = self._session_with_issue()
        session.edit_policy = "locked"
        session.save(update_fields=["edit_policy"])

        with self.assertRaises(IssueResolveError) as ctx:
            ResolveService.resolve(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                issue_id="ISS-1",
                action_id="ACT-SET",
                ctx={"actor": "test"},
            )
        self.assertEqual(ctx.exception.code, "locked")

    def test_resolve_surface_validation_errors(self) -> None:
        session = self._session_with_issue()
        issue = session.data["issues"][0]
        issue["context"]["actions"][0]["ops"][0]["qty"] = -5
        session.data["issues"] = [issue]
        session.save(update_fields=["data"])

        with self.assertRaises(IssueResolveError) as ctx:
            ResolveService.resolve(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                issue_id="ISS-1",
                action_id="ACT-SET",
                ctx={"actor": "test"},
            )
        self.assertEqual(ctx.exception.code, "invalid_qty")

    def test_resolve_wraps_unexpected_errors(self) -> None:
        class BoomResolver:
            source = "boom"

            def resolve(self, *, session, issue, action_id, ctx):
                raise RuntimeError("boom")

        registry.register_issue_resolver(BoomResolver())
        issue = {
            "id": "ISS-BOOM",
            "source": "boom",
            "code": "boom.fail",
            "blocking": True,
            "message": "boom",
            "context": {"actions": [{"id": "ACT-BOOM", "ops": [{"op": "set_qty", "line_id": "L-1", "qty": 1}]}]},
        }
        session = Session.objects.create(
            session_key="SESS-BOOM",
            channel=self.channel,
            state="open",
            pricing_policy=self.channel.pricing_policy,
            edit_policy="open",
            rev=0,
            items=[{"line_id": "L-1", "sku": "SKU", "qty": 1, "unit_price_q": 1000, "meta": {}}],
            data={"checks": {}, "issues": [issue]},
        )

        with self.assertRaises(IssueResolveError) as ctx:
            ResolveService.resolve(
                session_key=session.session_key,
                channel_ref=self.channel.ref,
                issue_id="ISS-BOOM",
                action_id="ACT-BOOM",
                ctx={"actor": "test"},
            )
        self.assertEqual(ctx.exception.code, "resolver_error")
