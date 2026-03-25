"""
Tests for fulfillment handlers — FulfillmentCreateHandler e FulfillmentUpdateHandler.

Covers: transitions, tracking enrichment, auto-sync, notifications, idempotency, errors.
"""

from __future__ import annotations

from django.test import TestCase
from django.utils import timezone
from shopman.ordering.models import Channel, Directive, Fulfillment, Order

from channels.handlers.fulfillment import (
    FulfillmentCreateHandler,
    FulfillmentUpdateHandler,
    _enrich_tracking_url,
)
from channels.topics import FULFILLMENT_CREATE, FULFILLMENT_UPDATE, NOTIFICATION_SEND


def _create_directive(**kwargs) -> Directive:
    """Create directive bypassing post_save signal."""
    objs = Directive.objects.bulk_create([Directive(**kwargs)])
    return objs[0]


def _make_channel(auto_sync=False, **overrides) -> Channel:
    config = {
        "flow": {
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "ready", "cancelled"],
                "processing": ["ready", "cancelled"],
                "ready": ["dispatched", "completed"],
                "dispatched": ["delivered", "returned"],
                "delivered": ["completed", "returned"],
                "completed": ["returned"],
                "cancelled": [],
                "returned": ["completed"],
            },
            "terminal_statuses": ["completed", "cancelled"],
            "auto_sync_fulfillment": auto_sync,
        },
    }
    defaults = {"ref": "test-ch", "name": "Test Channel", "config": config}
    defaults.update(overrides)
    return Channel.objects.create(**defaults)


def _make_order(channel, status="ready", **overrides) -> Order:
    defaults = {
        "ref": f"ORD-{timezone.now().timestamp():.0f}",
        "channel": channel,
        "status": status,
        "total_q": 5000,
        "data": {},
    }
    defaults.update(overrides)
    return Order.objects.create(**defaults)


def _make_fulfillment(order, status="pending", **overrides) -> Fulfillment:
    defaults = {"order": order, "status": status}
    defaults.update(overrides)
    return Fulfillment.objects.create(**defaults)


# ────────────────────────────────────────────────────────────────
# FulfillmentCreateHandler
# ────────────────────────────────────────────────────────────────


class FulfillmentCreateHandlerTests(TestCase):
    def setUp(self):
        self.channel = _make_channel()
        self.handler = FulfillmentCreateHandler()

    def test_topic(self):
        assert self.handler.topic == FULFILLMENT_CREATE

    def test_creates_fulfillment_flag(self):
        order = _make_order(self.channel)
        d = _create_directive(
            topic=FULFILLMENT_CREATE,
            payload={"order_ref": order.ref, "channel_ref": self.channel.ref},
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        order.refresh_from_db()
        assert d.status == "done"
        assert order.data["fulfillment_created"] is True

    def test_idempotent(self):
        order = _make_order(self.channel, data={"fulfillment_created": True})
        d = _create_directive(
            topic=FULFILLMENT_CREATE,
            payload={"order_ref": order.ref},
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "done"

    def test_missing_order_ref(self):
        d = _create_directive(topic=FULFILLMENT_CREATE, payload={})
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "failed"
        assert "missing order_ref" in d.last_error

    def test_order_not_found(self):
        d = _create_directive(
            topic=FULFILLMENT_CREATE, payload={"order_ref": "NOPE"}
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "failed"
        assert "not found" in d.last_error


# ────────────────────────────────────────────────────────────────
# FulfillmentUpdateHandler — transitions
# ────────────────────────────────────────────────────────────────


class FulfillmentUpdateTransitionTests(TestCase):
    def setUp(self):
        self.channel = _make_channel()
        self.handler = FulfillmentUpdateHandler()

    def test_topic(self):
        assert self.handler.topic == FULFILLMENT_UPDATE

    def test_pending_to_in_progress(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="pending")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "in_progress",
            },
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        ful.refresh_from_db()
        assert d.status == "done"
        assert ful.status == "in_progress"

    def test_in_progress_to_dispatched(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="in_progress")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
            },
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        ful.refresh_from_db()
        assert d.status == "done"
        assert ful.status == "dispatched"
        assert ful.dispatched_at is not None

    def test_dispatched_to_delivered(self):
        order = _make_order(self.channel, status="dispatched")
        ful = _make_fulfillment(order, status="dispatched")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "delivered",
            },
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        ful.refresh_from_db()
        assert d.status == "done"
        assert ful.status == "delivered"
        assert ful.delivered_at is not None

    def test_invalid_transition_fails(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="pending")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "delivered",
            },
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        ful.refresh_from_db()
        assert d.status == "failed"
        assert ful.status == "pending"

    def test_idempotent_already_at_target(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="dispatched")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
            },
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "done"

    def test_pending_to_cancelled(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="pending")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "cancelled",
            },
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        ful.refresh_from_db()
        assert d.status == "done"
        assert ful.status == "cancelled"


# ────────────────────────────────────────────────────────────────
# FulfillmentUpdateHandler — error cases
# ────────────────────────────────────────────────────────────────


class FulfillmentUpdateErrorTests(TestCase):
    def setUp(self):
        self.channel = _make_channel()
        self.handler = FulfillmentUpdateHandler()

    def test_missing_order_ref(self):
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={"fulfillment_id": 1, "new_status": "dispatched"},
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "failed"
        assert "missing order_ref" in d.last_error

    def test_missing_fulfillment_id(self):
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={"order_ref": "ORD-1", "new_status": "dispatched"},
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "failed"
        assert "missing fulfillment_id" in d.last_error

    def test_missing_new_status(self):
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={"order_ref": "ORD-1", "fulfillment_id": 1},
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "failed"
        assert "missing new_status" in d.last_error

    def test_order_not_found(self):
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={"order_ref": "NOPE", "fulfillment_id": 1, "new_status": "dispatched"},
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "failed"
        assert "Order not found" in d.last_error

    def test_fulfillment_not_found(self):
        order = _make_order(self.channel)
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": 99999,
                "new_status": "dispatched",
            },
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "failed"
        assert "Fulfillment not found" in d.last_error


# ────────────────────────────────────────────────────────────────
# FulfillmentUpdateHandler — tracking enrichment
# ────────────────────────────────────────────────────────────────


class FulfillmentTrackingTests(TestCase):
    def setUp(self):
        self.channel = _make_channel()
        self.handler = FulfillmentUpdateHandler()

    def test_tracking_code_and_carrier_stored(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="in_progress")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
                "tracking_code": "BR123456789",
                "carrier": "correios",
            },
        )
        self.handler.handle(message=d, ctx={})
        ful.refresh_from_db()
        assert ful.tracking_code == "BR123456789"
        assert ful.carrier == "correios"

    def test_auto_tracking_url_for_known_carrier(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="in_progress")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
                "tracking_code": "BR123456789",
                "carrier": "correios",
            },
        )
        self.handler.handle(message=d, ctx={})
        ful.refresh_from_db()
        assert "BR123456789" in ful.tracking_url
        assert "rastreamento.correios" in ful.tracking_url

    def test_no_tracking_url_for_unknown_carrier(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="in_progress")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
                "tracking_code": "XYZ123",
                "carrier": "moto_boy_jose",
            },
        )
        self.handler.handle(message=d, ctx={})
        ful.refresh_from_db()
        assert ful.tracking_url == ""

    def test_existing_tracking_url_not_overwritten(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(
            order,
            status="in_progress",
            tracking_url="https://custom.track/123",
            tracking_code="ABC",
            carrier="correios",
        )
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
            },
        )
        self.handler.handle(message=d, ctx={})
        ful.refresh_from_db()
        assert ful.tracking_url == "https://custom.track/123"


class TrackingUrlEnrichmentUnitTests(TestCase):
    def test_correios(self):
        url = _enrich_tracking_url("correios", "BR123")
        assert "BR123" in url
        assert "rastreamento.correios" in url

    def test_jadlog(self):
        url = _enrich_tracking_url("jadlog", "J456")
        assert "J456" in url
        assert "jadlog" in url

    def test_case_insensitive(self):
        url = _enrich_tracking_url("CORREIOS", "BR123")
        assert "BR123" in url

    def test_unknown_carrier_returns_empty(self):
        assert _enrich_tracking_url("random_carrier", "CODE") == ""

    def test_empty_code_returns_empty(self):
        assert _enrich_tracking_url("correios", "") == ""


# ────────────────────────────────────────────────────────────────
# FulfillmentUpdateHandler — auto-sync with Order
# ────────────────────────────────────────────────────────────────


class FulfillmentAutoSyncTests(TestCase):
    def setUp(self):
        self.handler = FulfillmentUpdateHandler()

    def test_sync_dispatched_when_enabled(self):
        channel = _make_channel(auto_sync=True)
        order = _make_order(channel, status="ready")
        ful = _make_fulfillment(order, status="in_progress")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
            },
        )
        self.handler.handle(message=d, ctx={})
        order.refresh_from_db()
        assert order.status == "dispatched"

    def test_sync_delivered_when_enabled(self):
        channel = _make_channel(auto_sync=True)
        order = _make_order(channel, status="dispatched")
        ful = _make_fulfillment(order, status="dispatched")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "delivered",
            },
        )
        self.handler.handle(message=d, ctx={})
        order.refresh_from_db()
        assert order.status == "delivered"

    def test_no_sync_when_disabled(self):
        channel = _make_channel(auto_sync=False)
        order = _make_order(channel, status="ready")
        ful = _make_fulfillment(order, status="in_progress")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
            },
        )
        self.handler.handle(message=d, ctx={})
        order.refresh_from_db()
        assert order.status == "ready"

    def test_no_sync_for_non_syncable_status(self):
        """in_progress não faz sync com Order (só dispatched/delivered)."""
        channel = _make_channel(auto_sync=True)
        order = _make_order(channel, status="ready")
        ful = _make_fulfillment(order, status="pending")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "in_progress",
            },
        )
        self.handler.handle(message=d, ctx={})
        order.refresh_from_db()
        assert order.status == "ready"

    def test_no_sync_if_order_cant_transition(self):
        """Order em 'new' não pode ir direto para 'dispatched'."""
        channel = _make_channel(auto_sync=True)
        order = _make_order(channel, status="new")
        ful = _make_fulfillment(order, status="in_progress")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
            },
        )
        self.handler.handle(message=d, ctx={})
        d.refresh_from_db()
        assert d.status == "done"
        order.refresh_from_db()
        assert order.status == "new"


# ────────────────────────────────────────────────────────────────
# FulfillmentUpdateHandler — notifications
# ────────────────────────────────────────────────────────────────


class FulfillmentNotificationTests(TestCase):
    def setUp(self):
        self.channel = _make_channel()
        self.handler = FulfillmentUpdateHandler()

    def test_dispatched_creates_notification(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="in_progress")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
                "tracking_code": "BR999",
                "carrier": "correios",
            },
        )
        initial_count = Directive.objects.filter(topic=NOTIFICATION_SEND).count()
        self.handler.handle(message=d, ctx={})
        notifs = Directive.objects.filter(topic=NOTIFICATION_SEND).exclude(pk__lte=initial_count)
        # Notification created
        assert notifs.exists()
        notif = notifs.first()
        assert notif.payload["template"] == "order_dispatched"
        assert notif.payload["order_ref"] == order.ref
        assert notif.payload["tracking"]["tracking_code"] == "BR999"
        assert notif.payload["tracking"]["carrier"] == "correios"
        assert "tracking_url" in notif.payload["tracking"]

    def test_delivered_creates_notification(self):
        order = _make_order(self.channel, status="dispatched")
        ful = _make_fulfillment(order, status="dispatched")
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "delivered",
            },
        )
        self.handler.handle(message=d, ctx={})
        notifs = Directive.objects.filter(
            topic=NOTIFICATION_SEND, payload__template="order_delivered"
        )
        assert notifs.exists()

    def test_in_progress_no_notification(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="pending")
        initial_count = Directive.objects.filter(topic=NOTIFICATION_SEND).count()
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "in_progress",
            },
        )
        self.handler.handle(message=d, ctx={})
        assert Directive.objects.filter(topic=NOTIFICATION_SEND).count() == initial_count

    def test_cancelled_no_notification(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="pending")
        initial_count = Directive.objects.filter(topic=NOTIFICATION_SEND).count()
        d = _create_directive(
            topic=FULFILLMENT_UPDATE,
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "cancelled",
            },
        )
        self.handler.handle(message=d, ctx={})
        assert Directive.objects.filter(topic=NOTIFICATION_SEND).count() == initial_count


# ────────────────────────────────────────────────────────────────
# Fulfillment model — auto timestamps
# ────────────────────────────────────────────────────────────────


class FulfillmentTimestampTests(TestCase):
    def setUp(self):
        self.channel = _make_channel()

    def test_dispatched_at_auto_set(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="in_progress")
        assert ful.dispatched_at is None
        ful.status = "dispatched"
        ful.save()
        assert ful.dispatched_at is not None

    def test_delivered_at_auto_set(self):
        order = _make_order(self.channel)
        ful = _make_fulfillment(order, status="dispatched")
        assert ful.delivered_at is None
        ful.status = "delivered"
        ful.save()
        assert ful.delivered_at is not None

    def test_dispatched_at_not_overwritten(self):
        order = _make_order(self.channel)
        ts = timezone.now()
        ful = _make_fulfillment(order, status="in_progress")
        ful.dispatched_at = ts
        ful.status = "dispatched"
        ful.save()
        assert ful.dispatched_at == ts
