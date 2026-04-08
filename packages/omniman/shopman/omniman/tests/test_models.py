"""Testes dos modelos do Ordering kernel."""

from decimal import Decimal

import pytest
from django.test import TestCase

from shopman.omniman.exceptions import InvalidTransition
from shopman.omniman.models import (
    Channel,
    Directive,
    Fulfillment,
    FulfillmentItem,
    IdempotencyKey,
    Order,
    OrderEvent,
    OrderItem,
    Session,
    SessionItem,
)


@pytest.mark.django_db
class TestChannel(TestCase):
    def test_create_channel(self):
        ch = Channel.objects.create(ref="pos", name="PDV")
        assert ch.ref == "pos"
        assert str(ch) == "PDV"

    def test_channel_defaults(self):
        ch = Channel.objects.create(ref="test")
        assert ch.pricing_policy == "internal"
        assert ch.edit_policy == "open"
        assert ch.is_active is True
        assert ch.config == {}


@pytest.mark.django_db
class TestSession(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(ref="pos", name="PDV")

    def test_create_session(self):
        session = Session.objects.create(
            session_key="S-1",
            channel=self.channel,
        )
        assert session.state == "open"
        assert session.rev == 0
        assert session.items == []

    def test_create_session_with_items(self):
        session = Session.objects.create(
            session_key="S-2",
            channel=self.channel,
            items=[{"sku": "CROISSANT", "qty": 2, "unit_price_q": 1000}],
        )
        items = session.items
        assert len(items) == 1
        assert items[0]["sku"] == "CROISSANT"
        assert items[0]["qty"] == Decimal("2")
        assert items[0]["unit_price_q"] == 1000
        assert items[0]["line_total_q"] == 2000
        assert items[0]["line_id"].startswith("L-")

    def test_session_items_cache_invalidation(self):
        session = Session.objects.create(
            session_key="S-3",
            channel=self.channel,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 100}],
        )
        items = session.items
        line_id = items[0]["line_id"]
        # Modify via SessionItem directly
        si = SessionItem.objects.get(session=session, line_id=line_id)
        si.qty = Decimal("5")
        si.save(update_fields=["qty"])
        # refresh_from_db reloads and invalidates cache
        session.refresh_from_db()
        new_items = session.items
        assert new_items[0]["qty"] == Decimal("5")

    def test_session_str_with_handle(self):
        session = Session.objects.create(
            session_key="S-4",
            channel=self.channel,
            handle_type="mesa",
            handle_ref="42",
        )
        assert str(session) == "Mesa: 42"

    def test_session_str_without_handle(self):
        session = Session.objects.create(
            session_key="S-5",
            channel=self.channel,
        )
        assert str(session) == "pos:S-5"


@pytest.mark.django_db
class TestOrder(TestCase):
    def setUp(self):
        self.channel = Channel.objects.create(ref="pos", name="PDV")

    def test_create_order(self):
        order = Order.objects.create(
            ref="ORD-TEST-001",
            channel=self.channel,
            session_key="S-1",
            total_q=5000,
        )
        assert order.status == "new"
        assert order.total_q == 5000

    def test_order_transition(self):
        order = Order.objects.create(
            ref="ORD-TEST-002",
            channel=self.channel,
        )
        order.transition_status("confirmed", actor="test")
        assert order.status == "confirmed"
        assert order.confirmed_at is not None

    def test_invalid_transition_raises(self):
        order = Order.objects.create(
            ref="ORD-TEST-003",
            channel=self.channel,
        )
        with pytest.raises(InvalidTransition):
            order.transition_status("completed", actor="test")

    def test_order_event_emitted_on_transition(self):
        order = Order.objects.create(
            ref="ORD-TEST-004",
            channel=self.channel,
        )
        order.transition_status("confirmed", actor="test")
        events = list(order.events.all())
        assert len(events) == 1
        assert events[0].type == "status_changed"
        assert events[0].payload["old_status"] == "new"
        assert events[0].payload["new_status"] == "confirmed"

    def test_emit_event(self):
        order = Order.objects.create(
            ref="ORD-TEST-005",
            channel=self.channel,
        )
        evt = order.emit_event("created", actor="system", payload={"key": "val"})
        assert evt.seq == 0
        assert evt.type == "created"

        evt2 = order.emit_event("note_added", actor="user")
        assert evt2.seq == 1


@pytest.mark.django_db
class TestOrderItem(TestCase):
    def test_create_order_item(self):
        ch = Channel.objects.create(ref="pos")
        order = Order.objects.create(ref="ORD-ITEM-001", channel=ch)
        item = OrderItem.objects.create(
            order=order,
            line_id="L-001",
            sku="SKU-A",
            qty=Decimal("2.5"),
            unit_price_q=1000,
            line_total_q=2500,
        )
        assert str(item) == "SKU-A x 2.5"


@pytest.mark.django_db
class TestDirective(TestCase):
    def test_create_directive(self):
        d = Directive.objects.create(
            topic="stock.hold",
            payload={"session_key": "S-1"},
        )
        assert d.status == "queued"
        assert d.attempts == 0


@pytest.mark.django_db
class TestFulfillment(TestCase):
    def test_fulfillment_lifecycle(self):
        ch = Channel.objects.create(ref="pos")
        order = Order.objects.create(ref="ORD-FF-001", channel=ch)
        ff = Fulfillment.objects.create(order=order)
        assert ff.status == "pending"

        ff.status = "in_progress"
        ff.save()
        assert ff.status == "in_progress"

        ff.status = "dispatched"
        ff.save()
        assert ff.status == "dispatched"

    def test_invalid_fulfillment_transition(self):
        ch = Channel.objects.create(ref="pos")
        order = Order.objects.create(ref="ORD-FF-002", channel=ch)
        ff = Fulfillment.objects.create(order=order)
        ff.status = "delivered"  # Skip dispatched
        with pytest.raises(InvalidTransition):
            ff.save()


@pytest.mark.django_db
class TestIdempotencyKey(TestCase):
    def test_create_idempotency_key(self):
        idem = IdempotencyKey.objects.create(scope="commit:pos", key="KEY-1")
        assert idem.status == "in_progress"
        assert str(idem) == "commit:pos:KEY-1"


@pytest.mark.django_db
class TestSessionItemsReadOnly(TestCase):
    """WP-H2: Session.items é read-only, update_items() persiste imediatamente."""

    def setUp(self):
        self.channel = Channel.objects.create(ref="h2-test", name="H2")
        self.session = Session.objects.create(
            session_key="H2-001",
            channel=self.channel,
            items=[{"sku": "A", "qty": 1, "unit_price_q": 100}],
        )

    def test_items_property_has_no_setter(self):
        """Atribuir a session.items levanta AttributeError."""
        with pytest.raises(AttributeError):
            self.session.items = [{"sku": "B", "qty": 1, "unit_price_q": 200}]

    def test_update_items_persists_to_database(self):
        """update_items() persiste imediatamente sem precisar de save()."""
        self.session.update_items([
            {"sku": "X", "qty": 3, "unit_price_q": 500},
        ])

        fresh = Session.objects.get(pk=self.session.pk)
        assert len(fresh.items) == 1
        assert fresh.items[0]["sku"] == "X"

    def test_save_does_not_persist_stale_items_cache(self):
        """save() não auto-persiste _items_cache (sem side effect oculto)."""
        self.session._items_cache = self.session._normalize_items([
            {"sku": "STALE", "qty": 1, "unit_price_q": 999},
        ])
        self.session.save()

        fresh = Session.objects.get(pk=self.session.pk)
        assert fresh.items[0]["sku"] == "A"

    def test_update_items_invalidates_and_refreshes_cache(self):
        """update_items() atualiza o cache interno."""
        self.session.update_items([
            {"sku": "NEW", "qty": 2, "unit_price_q": 300},
        ])

        assert len(self.session.items) == 1
        assert self.session.items[0]["sku"] == "NEW"
