"""Testes dos Services do Ordering kernel."""

from decimal import Decimal

import pytest
from django.test import TestCase

from shopman.ordering.exceptions import CommitError, SessionError, ValidationError
from shopman.ordering.models import Channel, Directive, Order, OrderItem, Session
from shopman.ordering.services import CommitService, ModifyService, SessionWriteService


@pytest.mark.django_db
class TestModifyService(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(ref="pos", name="PDV")
        self.session = Session.objects.create(
            session_key="S-1",
            channel=self.channel,
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
            channel=self.channel,
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
            channel=self.channel,
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
            channel=self.channel,
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
        self.channel = Channel.objects.create(ref="pos", name="PDV")

    def test_commit_creates_order(self):
        Session.objects.create(
            session_key="S-1",
            channel=self.channel,
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
            channel=self.channel,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 500}],
        )
        CommitService.commit(session_key="S-2", channel_ref="pos", idempotency_key="IDEM-2")
        session = Session.objects.get(session_key="S-2", channel=self.channel)
        assert session.state == "committed"

    def test_commit_idempotency(self):
        Session.objects.create(
            session_key="S-3",
            channel=self.channel,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 500}],
        )
        r1 = CommitService.commit(session_key="S-3", channel_ref="pos", idempotency_key="IDEM-3")
        r2 = CommitService.commit(session_key="S-3", channel_ref="pos", idempotency_key="IDEM-3")
        assert r1["order_ref"] == r2["order_ref"]

    def test_commit_empty_session_raises(self):
        Session.objects.create(session_key="S-4", channel=self.channel)
        with pytest.raises(CommitError, match="empty_session"):
            CommitService.commit(session_key="S-4", channel_ref="pos", idempotency_key="IDEM-4")

    def test_commit_blocking_issues_raises(self):
        Session.objects.create(
            session_key="S-5",
            channel=self.channel,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 100}],
        )
        session = Session.objects.get(session_key="S-5", channel=self.channel)
        session.data = {"issues": [{"id": "ISS-1", "source": "stock", "blocking": True, "message": "Sem estoque"}]}
        session.save()
        with pytest.raises(CommitError, match="blocking_issues"):
            CommitService.commit(session_key="S-5", channel_ref="pos", idempotency_key="IDEM-5")

    def test_commit_enqueues_post_commit_directives(self):
        """Commit with post_commit_directives enqueues the correct directives."""
        channel = Channel.objects.create(
            ref="pos-directives",
            name="PDV Directives",
            config={
                "post_commit_directives": ["stock.hold", "notification.send"],
            },
        )
        Session.objects.create(
            session_key="S-DIR-1",
            channel=channel,
            items=[{"sku": "CROISSANT", "qty": 2, "unit_price_q": 1000}],
        )
        result = CommitService.commit(
            session_key="S-DIR-1",
            channel_ref="pos-directives",
            idempotency_key="IDEM-DIR-1",
        )
        assert result["status"] == "committed"

        directives = list(Directive.objects.filter(
            payload__order_ref=result["order_ref"],
        ).order_by("pk"))
        assert len(directives) == 2

        # stock.hold directive
        stock_dir = directives[0]
        assert stock_dir.topic == "stock.hold"
        assert stock_dir.status == "queued"
        assert stock_dir.payload["channel_ref"] == "pos-directives"
        assert stock_dir.payload["rev"] == 0
        assert len(stock_dir.payload["items"]) == 1
        assert stock_dir.payload["items"][0]["sku"] == "CROISSANT"

        # notification.send directive
        notif_dir = directives[1]
        assert notif_dir.topic == "notification.send"
        assert notif_dir.status == "queued"
        assert notif_dir.payload["template"] == "order_received"

    def test_commit_no_directives_when_config_empty(self):
        """Commit with no post_commit_directives does not enqueue anything."""
        channel = Channel.objects.create(ref="bare", name="Bare")
        Session.objects.create(
            session_key="S-BARE-1",
            channel=channel,
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

    def test_commit_marketplace_only_notification(self):
        """Marketplace preset: only notification.send, no stock.hold."""
        channel = Channel.objects.create(
            ref="mktplace",
            name="Marketplace",
            config={
                "post_commit_directives": ["notification.send"],
            },
        )
        Session.objects.create(
            session_key="S-MKT-1",
            channel=channel,
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
        assert len(directives) == 1
        assert directives[0].topic == "notification.send"
        assert directives[0].payload["template"] == "order_received"


@pytest.mark.django_db
class TestSessionWriteService(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(ref="pos", name="PDV")

    def test_apply_check_result(self):
        session = Session.objects.create(session_key="S-1", channel=self.channel)
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
        Session.objects.create(session_key="S-2", channel=self.channel, rev=5)
        result = SessionWriteService.apply_check_result(
            session_key="S-2",
            channel_ref="pos",
            expected_rev=3,
            check_code="stock",
            check_payload={},
            issues=[],
        )
        assert result is False
