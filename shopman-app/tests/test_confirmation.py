"""
Tests for confirmation module.

Covers:
- ConfirmationService (config cascade)
- ConfirmationTimeoutHandler (auto-confirm)
- Hooks (on_order_created, on_order_status_changed, on_payment_confirmed)
- StockHoldTTL

Note: Tests that depend on payment module (PixGenerateHandler, PixTimeoutHandler)
are deferred to WP-R4 when the payment module is migrated.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from shopman.ordering import registry
from shopman.ordering.models import Channel, Directive, Order

from channels.backends.stock import NoopStockBackend
from channels.confirmation import (
    calculate_hold_ttl,
    get_confirmation_timeout,
    get_hold_expiration,
    get_pix_timeout,
    get_safety_margin,
    requires_manual_confirmation,
)
from channels.handlers.confirmation import ConfirmationTimeoutHandler
from channels.handlers.stock import StockHoldHandler
from channels.hooks import _on_order_created as on_order_created
from channels.hooks import on_order_lifecycle as on_order_status_changed
from channels.hooks import on_payment_confirmed
from channels.topics import CONFIRMATION_TIMEOUT, NOTIFICATION_SEND, PIX_GENERATE, STOCK_COMMIT


def _create_directive(**kwargs) -> Directive:
    """Create directive bypassing post_save signal (no auto-dispatch)."""
    objs = Directive.objects.bulk_create([Directive(**kwargs)])
    return objs[0]


def _make_whatsapp_channel(**overrides) -> Channel:
    """Cria um canal WhatsApp com config completa para testes (ChannelConfig format)."""
    config = {
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
        "notifications": {
            "backend": "manychat",
        },
        "flow": {
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "cancelled"],
                "processing": ["ready", "cancelled"],
                "ready": ["dispatched", "completed"],
                "dispatched": ["delivered"],
                "delivered": ["completed"],
                "completed": [],
                "cancelled": [],
            },
            "terminal_statuses": ["completed", "cancelled"],
            "auto_transitions": {
                "on_payment_confirm": "confirmed",
            },
        },
    }
    config.update(overrides.pop("config", {}))
    defaults = dict(ref="whatsapp", name="WhatsApp (Nice)", config=config)
    defaults.update(overrides)
    return Channel.objects.create(**defaults)


def _make_pdv_channel(**overrides) -> Channel:
    """Cria um canal PDV sem confirmação manual."""
    config = {
        "confirmation": {
            "mode": "immediate",
            "timeout_minutes": 5,
        },
        "pipeline": {
            "on_commit": ["customer.ensure"],
            "on_confirmed": ["stock.commit", "notification.send:order_confirmed"],
        },
        "notifications": {
            "backend": "console",
        },
        "flow": {
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "completed", "cancelled"],
                "processing": ["ready", "cancelled"],
                "ready": ["completed"],
                "completed": [],
                "cancelled": [],
            },
            "terminal_statuses": ["completed", "cancelled"],
        },
    }
    defaults = dict(ref="pdv", name="Balcão", config=config)
    defaults.update(overrides)
    return Channel.objects.create(**defaults)


def _make_order(channel: Channel, ref: str = "ORD-TEST-001", total_q: int = 3300, **kwargs) -> Order:
    """Cria um pedido de teste."""
    return Order.objects.create(
        ref=ref,
        channel=channel,
        total_q=total_q,
        status=Order.Status.NEW,
        data=kwargs.pop("data", {}),
        **kwargs,
    )


class ConfirmationServiceTests(TestCase):
    """Testes do service de configuração (cascata de config)."""

    def setUp(self) -> None:
        self.channel = _make_whatsapp_channel()

    def test_get_confirmation_timeout_from_channel_config(self):
        self.assertEqual(get_confirmation_timeout(self.channel), 5)

    def test_get_pix_timeout_from_channel_config(self):
        self.assertEqual(get_pix_timeout(self.channel), 10)

    def test_get_hold_expiration_from_channel_config(self):
        self.assertEqual(get_hold_expiration(self.channel), 20)

    def test_get_safety_margin_from_channel_config(self):
        self.assertEqual(get_safety_margin(self.channel), 2)

    def test_requires_manual_confirmation(self):
        self.assertTrue(requires_manual_confirmation(self.channel))

    def test_channel_config_uses_channel_config_defaults(self):
        """With ChannelConfig.effective(), bare channel gets ChannelConfig defaults."""
        channel = Channel.objects.create(ref="bare", name="Bare", config={})
        # ChannelConfig.Confirmation default is timeout_minutes=5
        self.assertEqual(get_confirmation_timeout(channel), 5)

    def test_channel_config_cascade_hardcoded_fallback(self):
        channel = Channel.objects.create(ref="bare2", name="Bare2", config={})
        self.assertEqual(get_confirmation_timeout(channel), 5)
        # ChannelConfig default for payment.timeout_minutes is 15
        self.assertEqual(get_pix_timeout(channel), 15)

    def test_safety_margin_per_product(self):
        product_data = {"safety_margin": 5}
        self.assertEqual(get_safety_margin(self.channel, product_data=product_data), 5)

    def test_pdv_has_no_safety_margin(self):
        pdv = _make_pdv_channel()
        self.assertEqual(get_safety_margin(pdv), 0)

    def test_safety_margin_reduces_remote_availability(self):
        available = 10
        margin = get_safety_margin(self.channel)
        remote_available = available - margin
        self.assertEqual(remote_available, 8)

    def test_calculate_hold_ttl_covers_full_cycle(self):
        ttl = calculate_hold_ttl(self.channel)
        confirm = get_confirmation_timeout(self.channel)
        pix = get_pix_timeout(self.channel)
        minimum = timedelta(minutes=confirm + pix + 5)
        self.assertGreaterEqual(ttl, minimum)

    def test_hold_ttl_at_least_20_minutes(self):
        ttl = calculate_hold_ttl(self.channel)
        self.assertEqual(ttl, timedelta(minutes=20))


class ConfirmationTimeoutHandlerTests(TestCase):
    """Testes do ConfirmationTimeoutHandler."""

    def setUp(self) -> None:
        self.channel = _make_whatsapp_channel()
        self.handler = ConfirmationTimeoutHandler()

    def test_confirmation_timeout_auto_confirms_order(self):
        order = _make_order(self.channel)
        expires_at = timezone.now() - timedelta(minutes=1)

        directive = _create_directive(
            topic=CONFIRMATION_TIMEOUT,
            payload={
                "order_ref": order.ref,
                "timeout_minutes": 5,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_confirmation_timeout_not_expired_yet(self):
        order = _make_order(self.channel)
        expires_at = timezone.now() + timedelta(minutes=3)

        directive = _create_directive(
            topic=CONFIRMATION_TIMEOUT,
            payload={
                "order_ref": order.ref,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertNotEqual(directive.status, "done")

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.NEW)

    def test_idempotent_confirmation_timeout(self):
        order = _make_order(self.channel)
        order.transition_status(Order.Status.CONFIRMED, actor="operator")

        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic=CONFIRMATION_TIMEOUT,
            payload={
                "order_ref": order.ref,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_confirmation_timeout_order_not_found(self):
        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic=CONFIRMATION_TIMEOUT,
            payload={
                "order_ref": "NONEXISTENT",
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_timeout_auto_confirms_with_holds(self):
        stock_backend = NoopStockBackend()
        registry.clear()
        registry.register_directive_handler(StockHoldHandler(backend=stock_backend))

        order = _make_order(self.channel, data={
            "holds": [
                {"hold_id": "hold-1", "sku": "SKU001", "qty": 2.0},
                {"hold_id": "hold-2", "sku": "SKU002", "qty": 1.0},
            ],
        })

        expires_at = timezone.now() - timedelta(minutes=1)
        directive = _create_directive(
            topic=CONFIRMATION_TIMEOUT,
            payload={
                "order_ref": order.ref,
                "expires_at": expires_at.isoformat(),
            },
        )

        self.handler.handle(message=directive, ctx={})

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def tearDown(self) -> None:
        registry.clear()


class HooksTests(TestCase):
    """Testes dos hooks de status change."""

    def setUp(self) -> None:
        self.channel = _make_whatsapp_channel()

    def test_on_order_created_creates_confirmation_timeout(self):
        order = _make_order(self.channel)

        on_order_created(order)

        directive = Directive.objects.filter(topic=CONFIRMATION_TIMEOUT).first()
        self.assertIsNotNone(directive)
        self.assertEqual(directive.payload["order_ref"], order.ref)
        self.assertIn("expires_at", directive.payload)

    def test_on_order_created_skips_pdv(self):
        pdv = _make_pdv_channel()
        order = _make_order(pdv, ref="ORD-PDV-001")

        on_order_created(order)

        self.assertEqual(Directive.objects.filter(topic=CONFIRMATION_TIMEOUT).count(), 0)

    def test_on_confirmed_creates_pix_generate(self):
        order = _make_order(self.channel)
        # transition_status fires order_changed signal → hooks.py creates pipeline directives
        order.transition_status(Order.Status.CONFIRMED, actor="operator")

        # Also call legacy hook explicitly
        on_order_status_changed(
            sender=Order,
            order=order,
            event_type="status_changed",
            actor="operator",
        )

        # At least one PIX_GENERATE directive should exist
        pix_count = Directive.objects.filter(topic=PIX_GENERATE).count()
        self.assertGreaterEqual(pix_count, 1)

        # At least one notification for order_confirmed
        notif = Directive.objects.filter(
            topic=NOTIFICATION_SEND, payload__template="order_confirmed"
        ).first()
        self.assertIsNotNone(notif)

    def test_webhook_triggers_auto_transition(self):
        order = _make_order(self.channel, data={
            "payment": {"intent_id": "pi_test", "status": "pending"},
        })

        on_payment_confirmed(order)

        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        self.assertEqual(order.data["payment"]["status"], "captured")

        notif = Directive.objects.filter(topic=NOTIFICATION_SEND, payload__template="payment_confirmed").first()
        self.assertIsNotNone(notif)

    def test_on_payment_confirmed_creates_stock_commit(self):
        order = _make_order(self.channel, data={
            "payment": {"intent_id": "pi_test", "status": "pending"},
            "holds": [
                {"hold_id": "h1", "sku": "SKU001", "qty": 2.0},
            ],
        })

        on_payment_confirmed(order)

        # Pipeline-driven: hooks.py creates stock.commit from pipeline config
        commit_directive = Directive.objects.filter(topic=STOCK_COMMIT).first()
        self.assertIsNotNone(commit_directive)
        self.assertEqual(commit_directive.payload["order_ref"], order.ref)


class StockHoldTTLTests(TestCase):
    """Testes do hold TTL configurável via channel config."""

    def test_hold_ttl_uses_channel_config(self):
        channel = _make_whatsapp_channel()
        ttl = calculate_hold_ttl(channel)
        self.assertEqual(ttl, timedelta(minutes=20))

    def test_hold_ttl_default_without_config(self):
        # Bare channel: ChannelConfig defaults → confirm=5, pix=15, margin=5 → min=25
        # hold_ttl=None → fallback=20, max(20, 25) = 25
        channel = Channel.objects.create(ref="bare3", name="Bare3", config={})
        ttl = calculate_hold_ttl(channel)
        self.assertEqual(ttl, timedelta(minutes=25))
