"""Testes dos Services do Orderman kernel."""

import types
from decimal import Decimal

import pytest
from django.test import TestCase
from shopman.orderman.exceptions import CommitError, SessionError, ValidationError
from shopman.orderman.models import Directive, Order, Session
from shopman.orderman.services import (
    CommitService,
    CustomerOrderHistoryService,
    ModifyService,
    SessionWriteService,
)


@pytest.mark.django_db
class TestModifyService(TestCase):
    def setUp(self):
        self.channel = types.SimpleNamespace(ref="pos", name="PDV")
        self.session = Session.objects.create(
            session_key="S-1",
            channel_ref=self.channel.ref,
        )

    def test_add_line(self):
        session = ModifyService.modify_session(
            session_key="S-1",
            channel_ref="pos",
            ops=[{"op": "add_line", "sku": "CROISSANT", "qty": 2}],
        )
        assert len(session.items) == 1
        assert session.items[0]["sku"] == "CROISSANT"
        assert session.rev == 1

    def test_remove_line(self):
        session = Session.objects.create(
            session_key="S-2",
            channel_ref=self.channel.ref,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 100}],
        )
        line_id = session.items[0]["line_id"]
        session = ModifyService.modify_session(
            session_key="S-2",
            channel_ref="pos",
            ops=[{"op": "remove_line", "line_id": line_id}],
        )
        assert len(session.items) == 0

    def test_set_qty(self):
        session = Session.objects.create(
            session_key="S-3",
            channel_ref=self.channel.ref,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 100}],
        )
        line_id = session.items[0]["line_id"]
        session = ModifyService.modify_session(
            session_key="S-3",
            channel_ref="pos",
            ops=[{"op": "set_qty", "line_id": line_id, "qty": 5}],
        )
        assert session.items[0]["qty"] == Decimal("5")

    def test_set_data(self):
        session = ModifyService.modify_session(
            session_key="S-1",
            channel_ref="pos",
            ops=[{"op": "set_data", "path": "customer.name", "value": "John"}],
        )
        assert session.data.get("customer", {}).get("name") == "John"

    def test_modify_committed_session_raises(self):
        self.session.state = "committed"
        self.session.save()
        with pytest.raises(SessionError, match="already_committed"):
            ModifyService.modify_session(
                session_key="S-1",
                channel_ref="pos",
                ops=[{"op": "add_line", "sku": "A", "qty": 1}],
            )

    def test_modify_locked_session_raises(self):
        self.session.edit_policy = "locked"
        self.session.save()
        with pytest.raises(SessionError, match="locked"):
            ModifyService.modify_session(
                session_key="S-1",
                channel_ref="pos",
                ops=[{"op": "add_line", "sku": "A", "qty": 1}],
            )

    def test_unsupported_op_raises(self):
        with pytest.raises(ValidationError, match="unsupported_op"):
            ModifyService.modify_session(
                session_key="S-1",
                channel_ref="pos",
                ops=[{"op": "nope"}],
            )

    def test_merge_lines(self):
        session = Session.objects.create(
            session_key="S-4",
            channel_ref=self.channel.ref,
            items=[
                {"sku": "A", "qty": 2, "unit_price_q": 100},
                {"sku": "A", "qty": 3, "unit_price_q": 100},
            ],
        )
        items = session.items
        session = ModifyService.modify_session(
            session_key="S-4",
            channel_ref="pos",
            ops=[{"op": "merge_lines", "from_line_id": items[0]["line_id"], "into_line_id": items[1]["line_id"]}],
        )
        assert len(session.items) == 1
        assert session.items[0]["qty"] == Decimal("5")


@pytest.mark.django_db
class TestCommitService(TestCase):
    def setUp(self):
        self.channel = types.SimpleNamespace(ref="pos", name="PDV")

    def test_commit_creates_order(self):
        Session.objects.create(
            session_key="S-1",
            channel_ref=self.channel.ref,
            items=[{"sku": "CROISSANT", "qty": 2, "unit_price_q": 1000}],
        )
        result = CommitService.commit(
            session_key="S-1",
            channel_ref="pos",
            idempotency_key="IDEM-1",
        )
        assert result["status"] == "committed"
        assert result["total_q"] == 2000

        order = Order.objects.get(ref=result["order_ref"])
        assert order.total_q == 2000
        assert order.items.count() == 1

    def test_commit_marks_session_committed(self):
        Session.objects.create(
            session_key="S-2",
            channel_ref=self.channel.ref,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 500}],
        )
        CommitService.commit(session_key="S-2", channel_ref="pos", idempotency_key="IDEM-2")
        session = Session.objects.get(session_key="S-2", channel_ref=self.channel.ref)
        assert session.state == "committed"

    def test_commit_seals_commitment_evidence_in_snapshot(self):
        Session.objects.create(
            session_key="S-COMMIT-1",
            channel_ref=self.channel.ref,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 500}],
            data={
                "checks": {
                    "stock": {
                        "rev": 0,
                        "at": "2026-04-12T12:00:00+00:00",
                        "result": {"approved": True, "holds": [{"hold_id": "H1"}]},
                    },
                    "other": {
                        "rev": 0,
                        "at": "2026-04-12T12:01:00+00:00",
                        "result": {"ok": True},
                    },
                },
                "issues": [],
            },
        )

        result = CommitService.commit(
            session_key="S-COMMIT-1",
            channel_ref="pos",
            idempotency_key="IDEM-COMMIT-1",
            channel_config={"rules": {"checks": ["stock"]}},
        )

        order = Order.objects.get(ref=result["order_ref"])
        commitment = order.snapshot["commitment"]
        assert commitment["session_rev"] == 0
        assert commitment["required_checks"] == ["stock"]
        assert "stock" in commitment["checks"]
        assert "other" not in commitment["checks"]
        assert commitment["checks"]["stock"]["result"]["approved"] is True

    def test_commit_idempotency(self):
        Session.objects.create(
            session_key="S-3",
            channel_ref=self.channel.ref,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 500}],
        )
        r1 = CommitService.commit(session_key="S-3", channel_ref="pos", idempotency_key="IDEM-3")
        r2 = CommitService.commit(session_key="S-3", channel_ref="pos", idempotency_key="IDEM-3")
        assert r1["order_ref"] == r2["order_ref"]

    def test_commit_empty_session_raises(self):
        Session.objects.create(session_key="S-4", channel_ref=self.channel.ref)
        with pytest.raises(CommitError, match="empty_session"):
            CommitService.commit(session_key="S-4", channel_ref="pos", idempotency_key="IDEM-4")

    def test_commit_blocking_issues_raises(self):
        Session.objects.create(
            session_key="S-5",
            channel_ref=self.channel.ref,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 100}],
        )
        session = Session.objects.get(session_key="S-5", channel_ref=self.channel.ref)
        session.data = {"issues": [{"id": "ISS-1", "source": "stock", "blocking": True, "message": "Sem estoque"}]}
        session.save()
        with pytest.raises(CommitError, match="blocking_issues"):
            CommitService.commit(session_key="S-5", channel_ref="pos", idempotency_key="IDEM-5")

    def test_commit_no_directives_from_core(self):
        """CommitService does not create directives — that's hooks.py's job."""
        channel = types.SimpleNamespace(ref="bare", name="Bare")
        Session.objects.create(
            session_key="S-BARE-1",
            channel_ref=channel.ref,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 500}],
        )
        result = CommitService.commit(
            session_key="S-BARE-1",
            channel_ref="bare",
            idempotency_key="IDEM-BARE-1",
        )
        assert result["status"] == "committed"
        directives = Directive.objects.filter(payload__order_ref=result["order_ref"])
        assert directives.count() == 0

    def test_commit_marketplace_no_directives(self):
        """Marketplace channel: CommitService creates no directives."""
        channel = types.SimpleNamespace(
            ref="mktplace",
            name="Marketplace",
        )
        Session.objects.create(
            session_key="S-MKT-1",
            channel_ref=channel.ref,
            items=[{"sku": "PIZZA", "qty": 1, "unit_price_q": 3500}],
        )
        result = CommitService.commit(
            session_key="S-MKT-1",
            channel_ref="mktplace",
            idempotency_key="IDEM-MKT-1",
        )
        directives = list(Directive.objects.filter(
            payload__order_ref=result["order_ref"],
        ))
        assert len(directives) == 0


@pytest.mark.django_db
class TestSessionWriteService(TestCase):
    def setUp(self):
        self.channel = types.SimpleNamespace(ref="pos", name="PDV")

    def test_apply_check_result(self):
        session = Session.objects.create(session_key="S-1", channel_ref=self.channel.ref)
        result = SessionWriteService.apply_check_result(
            session_key="S-1",
            channel_ref="pos",
            expected_rev=0,
            check_code="stock",
            check_payload={"status": "ok"},
            issues=[],
        )
        assert result is True
        session.refresh_from_db()
        assert "stock" in session.data.get("checks", {})

    def test_stale_rev_returns_false(self):
        Session.objects.create(session_key="S-2", channel_ref=self.channel.ref, rev=5)
        result = SessionWriteService.apply_check_result(
            session_key="S-2",
            channel_ref="pos",
            expected_rev=3,
            check_code="stock",
            check_payload={},
            issues=[],
        )
        assert result is False


@pytest.mark.django_db
class TestCustomerOrderHistoryService(TestCase):
    def test_reads_orders_via_customer_ref_contract(self):
        Order.objects.create(
            ref="ORD-HIST-001",
            channel_ref="web",
            session_key="sess-hist-1",
            status=Order.Status.COMPLETED,
            snapshot={"pricing": {"total_q": 2500}, "items": [{"sku": "SKU-1"}]},
            data={"customer_ref": "CUST-HIST-001"},
            total_q=2500,
        )
        Order.objects.create(
            ref="ORD-HIST-002",
            channel_ref="web",
            session_key="sess-hist-2",
            status=Order.Status.CANCELLED,
            snapshot={"pricing": {"total_q": 900}, "items": [{"sku": "SKU-2"}]},
            data={"customer_ref": "OTHER-CUST"},
            total_q=900,
        )

        orders = CustomerOrderHistoryService.list_customer_orders(
            "CUST-HIST-001",
            limit=10,
        )
        stats = CustomerOrderHistoryService.get_customer_stats("CUST-HIST-001")

        assert len(orders) == 1
        assert orders[0].order_ref == "ORD-HIST-001"
        assert stats.total_orders == 1
        assert stats.total_spent_q == 2500
