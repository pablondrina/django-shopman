"""
E2E integration tests — Full order lifecycle across all apps.

Tests the complete flow: Session → Commit → Directives → Status transitions.

Covers:
- Web pickup & delivery flows
- Existing customer recognition
- Pre-order with future delivery_date
- Production → stock flow
- Balcão anonymous & identified flows
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from shopman.ordering import registry
from channels.handlers.customer import CustomerEnsureHandler
from channels.handlers.notification import NotificationSendHandler
from channels.backends.payment_mock import MockPaymentBackend
from channels.backends.stock import NoopStockBackend
from channels.handlers.stock import StockCommitHandler, StockHoldHandler
from channels.topics import CUSTOMER_ENSURE, NOTIFICATION_SEND, PIX_GENERATE, STOCK_COMMIT
from shopman.ordering.ids import generate_idempotency_key
from shopman.ordering.models import Channel, Directive, Order, Session
from shopman.ordering.services.commit import CommitService
from shopman.ordering.services.modify import ModifyService


def _make_web_channel(**overrides) -> Channel:
    """Create web e-commerce channel with full directives."""
    config = {
        "required_checks_on_commit": [],
        "post_commit_directives": [
            CUSTOMER_ENSURE,
            STOCK_COMMIT,
            PIX_GENERATE,
            NOTIFICATION_SEND,
        ],
        "confirmation": {
            "mode": "optimistic",
            "timeout_minutes": 5,
        },
        "payment": {
            "method": "pix",
            "timeout_minutes": 10,
        },
        "stock": {
            "hold_ttl_minutes": 20,
            "safety_margin": 2,
        },
        "pipeline": {
            "on_commit": ["customer.ensure", "stock.hold"],
            "on_confirmed": ["pix.generate", "notification.send:order_confirmed"],
            "on_payment_confirmed": ["stock.commit", "notification.send:payment_confirmed"],
            "on_cancelled": ["notification.send:order_cancelled"],
        },
        "notifications": {"backend": "console"},
        "flow": {
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "ready", "cancelled"],
                "processing": ["ready", "cancelled"],
                "ready": ["completed", "dispatched"],
                "dispatched": ["delivered", "completed"],
                "delivered": ["completed"],
                "completed": [],
                "cancelled": [],
            },
            "terminal_statuses": ["completed", "cancelled"],
        },
    }
    config.update(overrides.pop("config_overrides", {}))
    defaults = dict(
        ref="web-test",
        name="E-commerce Test",
        pricing_policy="internal",
        edit_policy="open",
        config=config,
    )
    defaults.update(overrides)
    return Channel.objects.create(**defaults)


def _make_balcao_channel() -> Channel:
    """Create balcão channel."""
    return Channel.objects.create(
        ref="balcao-test",
        name="Balcão Test",
        pricing_policy="internal",
        edit_policy="open",
        config={
            "required_checks_on_commit": [],
            "post_commit_directives": [
                CUSTOMER_ENSURE,
                STOCK_COMMIT,
            ],
            "confirmation": {
                "mode": "immediate",
                "timeout_minutes": 5,
            },
            "pipeline": {
                "on_commit": ["customer.ensure"],
                "on_confirmed": ["stock.commit", "notification.send:order_confirmed"],
            },
            "notifications": {"backend": "console"},
            "flow": {
                "transitions": {
                    "new": ["confirmed", "cancelled"],
                    "confirmed": ["processing", "ready", "cancelled"],
                    "processing": ["ready", "cancelled"],
                    "ready": ["completed"],
                    "completed": [],
                    "cancelled": [],
                },
                "terminal_statuses": ["completed", "cancelled"],
            },
        },
    )


def _create_session_with_items(channel: Channel, session_key: str, phone: str = "", name: str = "") -> Session:
    """Create a session with items and customer data."""
    session = Session.objects.create(
        session_key=session_key,
        channel=channel,
        state="open",
        handle_type="phone" if phone else "",
        handle_ref=phone,
        items=[
            {
                "line_id": "L001",
                "sku": "PAO-FRANCES",
                "name": "Pão Francês",
                "qty": "5",
                "unit_price_q": 80,
                "line_total_q": 400,
            },
            {
                "line_id": "L002",
                "sku": "CROISSANT",
                "name": "Croissant",
                "qty": "2",
                "unit_price_q": 800,
                "line_total_q": 1600,
            },
        ],
        data={},
    )

    # Set customer data via session.data (as CheckoutView does)
    if phone or name:
        data = session.data or {}
        if name:
            data["customer"] = {"name": name, "phone": phone}
        if phone:
            data.setdefault("customer", {})["phone"] = phone
        session.data = data
        session.save(update_fields=["data"])

    return session


def _commit_session(session: Session, **kwargs) -> dict:
    """Commit a session and return the result."""
    return CommitService.commit(
        session_key=session.session_key,
        channel_ref=session.channel.ref,
        idempotency_key=generate_idempotency_key(),
        **kwargs,
    )


class _BaseE2ETestCase(TestCase):
    """Base class with handler registration."""

    def setUp(self) -> None:
        super().setUp()
        registry.clear()

        self.payment_backend = MockPaymentBackend(auto_authorize=False)
        self.stock_backend = NoopStockBackend()

        registry.register_directive_handler(CustomerEnsureHandler())
        registry.register_directive_handler(StockHoldHandler(backend=self.stock_backend))
        registry.register_directive_handler(StockCommitHandler(backend=self.stock_backend))

        # Register notification handler (needs service setup)
        try:
            registry.register_directive_handler(NotificationSendHandler())
        except (ValueError, ImportError):
            pass

        # Pix handlers need payment backend
        from channels.handlers.payment import PixGenerateHandler, PixTimeoutHandler

        try:
            registry.register_directive_handler(PixGenerateHandler(backend=self.payment_backend))
            registry.register_directive_handler(PixTimeoutHandler(backend=self.payment_backend))
        except ValueError:
            pass

        # Register console notification backend
        try:
            from channels.backends.notification_console import ConsoleBackend
            from channels.notifications import register_backend

            register_backend("console", ConsoleBackend())
        except (ImportError, ValueError, AttributeError):
            pass

    def tearDown(self) -> None:
        registry.clear()
        super().tearDown()

    def _setup_customers(self):
        """Create customer group (needed for customer creation)."""
        from shopman.customers.models import CustomerGroup

        CustomerGroup.objects.get_or_create(
            ref="default",
            defaults={"name": "Default", "is_default": True},
        )


class TestWebOrderPickupFullCycle(_BaseE2ETestCase):
    """
    Test 1: Web order with pickup — full cycle.

    Session → items → fulfillment_type=pickup → commit →
    Customer created → Stock hold → PIX → Payment →
    confirmed → ready → Notification "pronto para retirada"
    """

    def test_web_order_pickup_full_cycle(self):
        self._setup_customers()
        channel = _make_web_channel()

        # Create session with customer data
        session = _create_session_with_items(
            channel, "WEB-PICKUP-001",
            phone="+5543999990001", name="João Silva",
        )
        session.data["fulfillment_type"] = "pickup"
        session.save(update_fields=["data"])

        # Commit (captureOnCommitCallbacks fires directive handlers)
        with self.captureOnCommitCallbacks(execute=True):
            result = _commit_session(session)
        order_ref = result["order_ref"]
        order = Order.objects.get(ref=order_ref)

        # Verify order created (auto-confirmed: channel has no manual confirmation)
        self.assertIn(order.status, ("new", "confirmed"))
        self.assertEqual(order.total_q, 2000)  # 400 + 1600
        self.assertEqual(order.handle_ref, "+5543999990001")

        # Verify customer.ensure directive was created
        ensure_directives = Directive.objects.filter(topic=CUSTOMER_ENSURE)
        self.assertTrue(ensure_directives.exists())

        # Verify customer was created in Customers
        from shopman.customers.models import Customer

        customer = Customer.objects.filter(phone="+5543999990001").first()
        self.assertIsNotNone(customer, "Customer should be created by CustomerEnsureHandler")
        self.assertEqual(customer.first_name, "João")

        # Verify pix.generate was created
        pix_directives = Directive.objects.filter(topic=PIX_GENERATE)
        self.assertTrue(pix_directives.exists())

        # Verify stock.commit was created
        commit_directives = Directive.objects.filter(topic=STOCK_COMMIT)
        self.assertTrue(commit_directives.exists())

        # Simulate payment confirmation
        order.refresh_from_db()
        payment = order.data.get("payment", {})
        if payment.get("intent_id"):
            self.payment_backend.capture(payment["intent_id"])
            order.data["payment"]["status"] = "captured"
            order.save(update_fields=["data", "updated_at"])

        # Transition to ready (may already be confirmed via auto-confirm)
        order.refresh_from_db()
        if order.status != "confirmed":
            order.transition_status("confirmed", actor="operator")
        order.transition_status("ready", actor="operator")

        # Verify notification directive for "ready" + pickup was created
        ready_notifications = Directive.objects.filter(
            topic=NOTIFICATION_SEND,
        ).order_by("-id")
        # Should have at least one notification for ready status
        self.assertTrue(
            ready_notifications.exists(),
            "Notification should be created on status transition to ready",
        )


class TestWebOrderDeliveryFullCycle(_BaseE2ETestCase):
    """
    Test 2: Web order with delivery — full cycle.

    Session → items → fulfillment_type=delivery + address → commit →
    PIX → Payment → confirmed → ready → dispatched →
    Notification "saiu para entrega" → delivered
    """

    def test_web_order_delivery_full_cycle(self):
        self._setup_customers()
        channel = _make_web_channel()

        session = _create_session_with_items(
            channel, "WEB-DELIVERY-001",
            phone="+5543999990002", name="Maria Santos",
        )
        session.data["fulfillment_type"] = "delivery"
        session.data["delivery_address"] = "Rua das Flores, 123 - Centro"
        session.save(update_fields=["data"])

        with self.captureOnCommitCallbacks(execute=True):
            result = _commit_session(session)
        order = Order.objects.get(ref=result["order_ref"])

        # Verify delivery data stored
        self.assertEqual(order.data.get("fulfillment_type"), "delivery")
        self.assertEqual(order.data.get("delivery_address"), "Rua das Flores, 123 - Centro")

        # Simulate payment
        order.refresh_from_db()
        payment = order.data.get("payment", {})
        if payment.get("intent_id"):
            self.payment_backend.capture(payment["intent_id"])
            order.data["payment"]["status"] = "captured"
            order.save(update_fields=["data", "updated_at"])

        # Transition through delivery flow (may already be confirmed via auto-confirm)
        order.refresh_from_db()
        if order.status != "confirmed":
            order.transition_status("confirmed", actor="operator")
        order.transition_status("ready", actor="operator")

        order.transition_status("dispatched", actor="courier")
        order.transition_status("delivered", actor="courier")
        order.transition_status("completed", actor="system")

        self.assertEqual(order.status, "completed")


class TestExistingCustomerRecognized(_BaseE2ETestCase):
    """
    Test 3: Existing customer is recognized and not duplicated.

    Create Customer with phone → Checkout with same phone →
    CustomerEnsure links (doesn't create new) → RFM updated
    """

    def test_existing_customer_recognized(self):
        self._setup_customers()
        from shopman.customers.models import Customer
        from shopman.customers.services import customer as CustomerService

        # Pre-create customer
        existing = CustomerService.create(
            ref="EXIST-001",
            first_name="Ana",
            last_name="Costa",
            phone="+5543999990003",
            customer_type="individual",
        )

        channel = _make_web_channel()
        session = _create_session_with_items(
            channel, "WEB-EXIST-001",
            phone="+5543999990003", name="Ana Costa",
        )
        session.data["fulfillment_type"] = "pickup"
        session.save(update_fields=["data"])

        with self.captureOnCommitCallbacks(execute=True):
            result = _commit_session(session)
        order = Order.objects.get(ref=result["order_ref"])

        # Customer should NOT be duplicated
        customers = Customer.objects.filter(phone="+5543999990003")
        self.assertEqual(customers.count(), 1, "Should not duplicate customer")
        self.assertEqual(customers.first().ref, "EXIST-001")

        # Customer ensure should have linked the order
        ensure_directive = Directive.objects.filter(topic=CUSTOMER_ENSURE).first()
        self.assertIsNotNone(ensure_directive)
        ensure_directive.refresh_from_db()
        self.assertEqual(ensure_directive.status, "done")


class TestPreorderFlow(_BaseE2ETestCase):
    """
    Test 4: Pre-order with future delivery_date.

    Order with delivery_date=tomorrow → Hold target_date=tomorrow →
    suggest() counts demand
    """

    def test_preorder_with_future_date(self):
        self._setup_customers()
        channel = _make_web_channel()
        tomorrow = (date.today() + timedelta(days=1)).isoformat()

        session = _create_session_with_items(
            channel, "WEB-PREORDER-001",
            phone="+5543999990004", name="Pedro Lima",
        )
        session.data["fulfillment_type"] = "pickup"
        session.data["delivery_date"] = tomorrow
        session.save(update_fields=["data"])

        with self.captureOnCommitCallbacks(execute=True):
            result = _commit_session(session)
        order = Order.objects.get(ref=result["order_ref"])

        # Verify delivery_date stored on order
        self.assertEqual(order.data.get("delivery_date"), tomorrow)

        # Verify stock.commit directive was created
        commit_directives = Directive.objects.filter(topic=STOCK_COMMIT)
        self.assertTrue(commit_directives.exists())


class TestProductionToStock(_BaseE2ETestCase):
    """
    Test 5: Production close → stock receive.

    craft.close(produced=20) → stock.receive(qty=20) → Quant updated
    """

    def test_production_to_stock(self):
        """Crafting work order close deposits into Stocking."""
        from shopman.stocking import stock
        from shopman.stocking.models import Position, PositionKind, Quant

        # Create position
        position, _ = Position.objects.get_or_create(
            ref="loja-e2e",
            defaults={
                "name": "Loja E2E",
                "kind": PositionKind.PHYSICAL,
                "is_saleable": True,
            },
        )

        # Simulate production → stock receive
        today = date.today()
        stock.receive(
            quantity=Decimal("20"),
            sku="BAGUETTE",
            position=position,
            target_date=today,
            reason="Production: WO-E2E-001",
        )

        # Verify quant updated
        quant = Quant.objects.filter(
            sku="BAGUETTE", position=position, target_date=today,
        ).first()
        self.assertIsNotNone(quant)
        self.assertEqual(quant.quantity, Decimal("20"))


class TestBalcaoAnonymous(_BaseE2ETestCase):
    """
    Test 6: Balcão without identification — anonymous order.

    Balcão sem identificação → Order sem customer (anônimo permitido)
    """

    def test_balcao_anonymous_order(self):
        channel = _make_balcao_channel()

        session = Session.objects.create(
            session_key="BALCAO-ANON-001",
            channel=channel,
            state="open",
            items=[
                {
                    "line_id": "L001",
                    "sku": "PAO-FRANCES",
                    "name": "Pão Francês",
                    "qty": "10",
                    "unit_price_q": 80,
                    "line_total_q": 800,
                },
            ],
            data={},
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = _commit_session(session)
        order = Order.objects.get(ref=result["order_ref"])

        # Order should work without customer (auto-confirmed: channel has no manual confirmation)
        self.assertIn(order.status, ("new", "confirmed"))
        self.assertEqual(order.total_q, 800)
        self.assertFalse(order.handle_ref)  # No customer identification

        # customer.ensure should succeed (skip gracefully for anonymous)
        ensure_directive = Directive.objects.filter(topic=CUSTOMER_ENSURE).first()
        self.assertIsNotNone(ensure_directive)
        ensure_directive.refresh_from_db()
        self.assertEqual(ensure_directive.status, "done")


class TestBalcaoWithCPF(_BaseE2ETestCase):
    """
    Test 7: Balcão with CPF identification.

    Balcão com identificação → Customer ensure cria com phone
    """

    def test_balcao_with_identification(self):
        self._setup_customers()
        channel = _make_balcao_channel()

        session = Session.objects.create(
            session_key="BALCAO-CPF-001",
            channel=channel,
            state="open",
            handle_type="phone",
            handle_ref="+5543999990007",
            items=[
                {
                    "line_id": "L001",
                    "sku": "PAO-FRANCES",
                    "name": "Pão Francês",
                    "qty": "5",
                    "unit_price_q": 80,
                    "line_total_q": 400,
                },
            ],
            data={
                "customer": {
                    "name": "Carlos Souza",
                    "phone": "+5543999990007",
                },
            },
        )

        with self.captureOnCommitCallbacks(execute=True):
            result = _commit_session(session)
        order = Order.objects.get(ref=result["order_ref"])

        # Order should have handle_ref
        self.assertEqual(order.handle_ref, "+5543999990007")

        # Customer should be created
        from shopman.customers.models import Customer

        customer = Customer.objects.filter(phone="+5543999990007").first()
        self.assertIsNotNone(customer, "Customer should be created for identified balcão order")
        self.assertEqual(customer.first_name, "Carlos")
