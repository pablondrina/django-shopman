"""
Tests for checkout defaults — service, handler, and view integration.

Covers:
- get_defaults returns empty for new customer
- save_defaults + get_defaults round-trip
- Defaults scoped by channel (isolation)
- Inference after 3+ orders with consistent patterns
- Explicit preferences not overwritten by inferred
- Handler processes directive correctly
- Handler skips when customer_ref missing
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase
from django.utils import timezone

from channels.backends.checkout_defaults import (
    CATEGORY,
    MIN_ORDERS_FOR_INFERENCE,
    CheckoutDefaultsService,
)
from channels.handlers.checkout_defaults import CheckoutInferDefaultsHandler
from channels.topics import CHECKOUT_INFER_DEFAULTS
from shopman.customers.contrib.preferences.models import CustomerPreference, PreferenceType
from shopman.customers.models import Customer
from shopman.ordering.models import Channel, Directive, Order


def _create_directive(**kwargs) -> Directive:
    """Create directive bypassing post_save signal."""
    objs = Directive.objects.bulk_create([Directive(**kwargs)])
    return objs[0]


class CheckoutDefaultsServiceTests(TestCase):
    """Tests for CheckoutDefaultsService."""

    def setUp(self):
        self.customer = Customer.objects.create(
            ref="CUST-CD-001", first_name="Maria", phone="5543999990001",
        )
        self.channel = Channel.objects.create(
            ref="web", name="Loja Online", config={},
        )

    def test_get_defaults_empty(self):
        """New customer has no checkout defaults."""
        defaults = CheckoutDefaultsService.get_defaults("CUST-CD-001", "web")
        self.assertEqual(defaults, {})

    def test_save_and_get_defaults(self):
        """Save explicit defaults and retrieve them."""
        CheckoutDefaultsService.save_defaults(
            customer_ref="CUST-CD-001",
            channel_ref="web",
            data={
                "fulfillment_type": "delivery",
                "payment_method": "pix",
                "order_notes": "Sem glúten separado",
            },
            source="order:ORD-001",
        )

        defaults = CheckoutDefaultsService.get_defaults("CUST-CD-001", "web")
        self.assertEqual(defaults["fulfillment_type"], "delivery")
        self.assertEqual(defaults["payment_method"], "pix")
        self.assertEqual(defaults["order_notes"], "Sem glúten separado")

    def test_save_overwrites_previous(self):
        """Saving again updates the preference."""
        CheckoutDefaultsService.save_defaults(
            "CUST-CD-001", "web", {"fulfillment_type": "delivery"},
        )
        CheckoutDefaultsService.save_defaults(
            "CUST-CD-001", "web", {"fulfillment_type": "pickup"},
        )
        defaults = CheckoutDefaultsService.get_defaults("CUST-CD-001", "web")
        self.assertEqual(defaults["fulfillment_type"], "pickup")

    def test_defaults_scoped_by_channel(self):
        """Defaults for one channel don't leak to another."""
        Channel.objects.create(ref="whatsapp", name="WhatsApp", config={})

        CheckoutDefaultsService.save_defaults(
            "CUST-CD-001", "web", {"fulfillment_type": "delivery"},
        )
        CheckoutDefaultsService.save_defaults(
            "CUST-CD-001", "whatsapp", {"fulfillment_type": "pickup"},
        )

        web_defaults = CheckoutDefaultsService.get_defaults("CUST-CD-001", "web")
        wa_defaults = CheckoutDefaultsService.get_defaults("CUST-CD-001", "whatsapp")

        self.assertEqual(web_defaults["fulfillment_type"], "delivery")
        self.assertEqual(wa_defaults["fulfillment_type"], "pickup")

    def test_empty_values_not_saved(self):
        """Empty string values are not saved."""
        CheckoutDefaultsService.save_defaults(
            "CUST-CD-001", "web",
            {"fulfillment_type": "delivery", "order_notes": ""},
        )
        defaults = CheckoutDefaultsService.get_defaults("CUST-CD-001", "web")
        self.assertIn("fulfillment_type", defaults)
        self.assertNotIn("order_notes", defaults)

    def test_unknown_keys_ignored(self):
        """Keys not in KEYS list are silently ignored."""
        CheckoutDefaultsService.save_defaults(
            "CUST-CD-001", "web",
            {"fulfillment_type": "delivery", "unknown_field": "value"},
        )
        defaults = CheckoutDefaultsService.get_defaults("CUST-CD-001", "web")
        self.assertNotIn("unknown_field", defaults)


class CheckoutDefaultsInferenceTests(TestCase):
    """Tests for inference from order history."""

    def setUp(self):
        self.customer = Customer.objects.create(
            ref="CUST-INF-001", first_name="Carlos", phone="5543999990002",
        )
        self.channel = Channel.objects.create(
            ref="web", name="Loja Online", config={},
        )

    def _make_orders(self, count, data_overrides=None):
        """Create N orders with consistent checkout data."""
        orders = []
        base_data = {
            "customer_ref": "CUST-INF-001",
            "fulfillment_type": "delivery",
            "delivery_address": "Rua X 123",
            "delivery_time_slot": "manha",
            "payment": {"method": "pix"},
        }
        if data_overrides:
            base_data.update(data_overrides)

        for i in range(count):
            order = Order.objects.create(
                ref=f"ORD-INF-{i:03d}",
                channel=self.channel,
                status="completed",
                total_q=1000,
                handle_type="phone",
                handle_ref="5543999990002",
                data=dict(base_data),
            )
            # Backdate for timing inference
            Order.objects.filter(pk=order.pk).update(
                created_at=timezone.now() - timedelta(days=count - i),
            )
            order.refresh_from_db()
            orders.append(order)
        return orders

    def test_no_inference_below_threshold(self):
        """No inference with fewer than MIN_ORDERS_FOR_INFERENCE orders."""
        orders = self._make_orders(MIN_ORDERS_FOR_INFERENCE - 1)
        inferred = CheckoutDefaultsService.infer_from_history(
            "CUST-INF-001", "web", orders,
        )
        self.assertEqual(inferred, {})

    def test_infer_defaults_after_threshold(self):
        """Infer defaults when all orders have the same pattern."""
        orders = self._make_orders(4)
        inferred = CheckoutDefaultsService.infer_from_history(
            "CUST-INF-001", "web", orders,
        )
        self.assertEqual(inferred["fulfillment_type"], "delivery")
        self.assertEqual(inferred["delivery_time_slot"], "manha")
        self.assertEqual(inferred["payment_method"], "pix")

    def test_no_inference_below_confidence(self):
        """No inference when values are too diverse (below 70%)."""
        # 2 delivery + 2 pickup = 50% each → below threshold
        orders = []
        for i in range(4):
            ft = "delivery" if i < 2 else "pickup"
            order = Order.objects.create(
                ref=f"ORD-DIV-{i:03d}",
                channel=self.channel,
                status="completed",
                total_q=1000,
                data={"customer_ref": "CUST-INF-001", "fulfillment_type": ft},
            )
            orders.append(order)

        inferred = CheckoutDefaultsService.infer_from_history(
            "CUST-INF-001", "web", orders,
        )
        self.assertNotIn("fulfillment_type", inferred)

    def test_explicit_not_overwritten_by_inferred(self):
        """Explicit preferences are never overwritten by inference."""
        # Save explicit first
        CheckoutDefaultsService.save_defaults(
            "CUST-INF-001", "web", {"fulfillment_type": "pickup"},
        )

        # Create orders all with delivery
        orders = self._make_orders(5)
        inferred = CheckoutDefaultsService.infer_from_history(
            "CUST-INF-001", "web", orders,
        )

        # fulfillment_type should NOT be inferred (explicit exists)
        self.assertNotIn("fulfillment_type", inferred)

        # But the explicit value should remain
        defaults = CheckoutDefaultsService.get_defaults("CUST-INF-001", "web")
        self.assertEqual(defaults["fulfillment_type"], "pickup")

    def test_inferred_preference_has_correct_type(self):
        """Inferred preferences are saved with type=inferred and confidence."""
        orders = self._make_orders(4)
        CheckoutDefaultsService.infer_from_history("CUST-INF-001", "web", orders)

        pref = CustomerPreference.objects.get(
            customer=self.customer,
            category=CATEGORY,
            key="web:fulfillment_type",
        )
        self.assertEqual(pref.preference_type, PreferenceType.INFERRED)
        self.assertEqual(pref.confidence, Decimal("1.00"))


class CheckoutInferDefaultsHandlerTests(TestCase):
    """Tests for the directive handler."""

    def setUp(self):
        self.handler = CheckoutInferDefaultsHandler()
        self.customer = Customer.objects.create(
            ref="CUST-HDL-001", first_name="Ana", phone="5543999990003",
        )
        self.channel = Channel.objects.create(
            ref="web", name="Loja Online", config={},
        )

    def test_handler_topic(self):
        self.assertEqual(self.handler.topic, CHECKOUT_INFER_DEFAULTS)

    def test_handler_missing_order_ref(self):
        """Handler fails gracefully with missing order_ref."""
        directive = _create_directive(
            topic=CHECKOUT_INFER_DEFAULTS,
            payload={},
        )
        self.handler.handle(message=directive, ctx={})
        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("missing order_ref", directive.last_error)

    def test_handler_order_not_found(self):
        """Handler fails gracefully when order doesn't exist."""
        directive = _create_directive(
            topic=CHECKOUT_INFER_DEFAULTS,
            payload={"order_ref": "NONEXISTENT"},
        )
        self.handler.handle(message=directive, ctx={})
        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")

    def test_handler_skips_without_customer_ref(self):
        """Handler marks done when order has no customer_ref yet."""
        order = Order.objects.create(
            ref="ORD-HDL-001",
            channel=self.channel,
            status="new",
            total_q=1000,
            data={},
        )
        directive = _create_directive(
            topic=CHECKOUT_INFER_DEFAULTS,
            payload={"order_ref": "ORD-HDL-001"},
        )
        self.handler.handle(message=directive, ctx={})
        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_handler_processes_with_history(self):
        """Handler completes successfully with enough order history."""
        # Create historical orders
        for i in range(4):
            Order.objects.create(
                ref=f"ORD-HIST-{i:03d}",
                channel=self.channel,
                status="completed",
                total_q=1000,
                data={
                    "customer_ref": "CUST-HDL-001",
                    "fulfillment_type": "delivery",
                    "payment": {"method": "pix"},
                },
            )

        # Current order (the one triggering inference)
        order = Order.objects.create(
            ref="ORD-HDL-002",
            channel=self.channel,
            status="new",
            total_q=1000,
            data={
                "customer_ref": "CUST-HDL-001",
                "fulfillment_type": "delivery",
                "payment": {"method": "pix"},
            },
        )

        directive = _create_directive(
            topic=CHECKOUT_INFER_DEFAULTS,
            payload={"order_ref": "ORD-HDL-002"},
        )
        self.handler.handle(message=directive, ctx={})
        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        # Verify preferences were inferred
        defaults = CheckoutDefaultsService.get_defaults("CUST-HDL-001", "web")
        self.assertEqual(defaults.get("fulfillment_type"), "delivery")
        self.assertEqual(defaults.get("payment_method"), "pix")
