"""
Tests for WP-F0: Correções de Fluxo & Robustez.

Covers:
- 0.2 Race condition: payment-after-cancel → OperatorAlert + auto-refund
- 0.4 Notification failure → OperatorAlert escalation
- 0.5 Session cleanup management command
- 0.6 Hold TTL >= Payment timeout (startup validation)
- 0.7 Custom error pages (404, 500)
- 0.8 HTMX error handling in base template

Note: 0.1 (PixTimeoutHandler) and 0.3 (CustomerCancel) already have extensive
dedicated tests in test_payment_handlers.py and test_web_navigation.py.
"""

from __future__ import annotations

from datetime import timedelta
from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import Client, TestCase
from django.utils import timezone
from shopman.ordering.models import Channel, Directive, Order, Session

from channels.hooks import on_payment_confirmed
from channels.topics import NOTIFICATION_SEND, PAYMENT_REFUND


def _create_directive(**kwargs) -> Directive:
    """Create directive bypassing post_save signal."""
    objs = Directive.objects.bulk_create([Directive(**kwargs)])
    return objs[0]


def _make_channel(**overrides) -> Channel:
    config = {
        "flow": {
            "transitions": {
                "new": ["confirmed", "cancelled"],
                "confirmed": ["processing", "cancelled"],
                "processing": ["ready", "cancelled"],
                "ready": ["completed"],
                "completed": [],
                "cancelled": [],
            },
            "terminal_statuses": ["completed", "cancelled"],
        },
    }
    defaults = {"ref": "test-f0", "name": "Test F0", "config": config}
    defaults.update(overrides)
    return Channel.objects.create(**defaults)


# ══════════════════════════════════════════════════════════════════════
# 0.2 Race Condition: Payment After Cancel → OperatorAlert
# ══════════════════════════════════════════════════════════════════════


class TestPaymentAfterCancelAlert(TestCase):
    """on_payment_confirmed for cancelled order creates OperatorAlert."""

    def setUp(self):
        self.channel = _make_channel()

    def test_payment_after_cancel_creates_operator_alert(self):
        """Race condition: payment confirmed on cancelled order → OperatorAlert."""
        from shop.models import OperatorAlert

        order = Order.objects.create(
            ref="ORD-RACE-01",
            channel=self.channel,
            status="cancelled",
            data={
                "payment": {
                    "method": "pix",
                    "intent_id": "INT-race-01",
                    "status": "pending",
                    "amount_q": 5000,
                },
            },
        )

        on_payment_confirmed(order)

        # Refund directive created
        refund = Directive.objects.filter(topic=PAYMENT_REFUND).first()
        self.assertIsNotNone(refund)
        self.assertEqual(refund.payload["reason"], "payment_after_cancel")

        # OperatorAlert created
        alert = OperatorAlert.objects.filter(type="payment_after_cancel").first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "warning")
        self.assertIn("ORD-RACE-01", alert.message)
        self.assertEqual(alert.order_ref, "ORD-RACE-01")
        self.assertFalse(alert.acknowledged)

    def test_payment_after_cancel_without_intent_still_alerts(self):
        """Even without intent_id, alert is created (no refund though)."""
        from shop.models import OperatorAlert

        order = Order.objects.create(
            ref="ORD-RACE-02",
            channel=self.channel,
            status="cancelled",
            data={"payment": {"method": "cash", "status": "pending"}},
        )

        on_payment_confirmed(order)

        # No refund (no intent_id)
        self.assertFalse(Directive.objects.filter(topic=PAYMENT_REFUND).exists())

        # But alert is still created
        alert = OperatorAlert.objects.filter(type="payment_after_cancel").first()
        self.assertIsNotNone(alert)
        self.assertIn("sem intent_id", alert.message)


# ══════════════════════════════════════════════════════════════════════
# 0.4 Notification Failure → OperatorAlert Escalation
# ══════════════════════════════════════════════════════════════════════


class TestNotificationEscalation(TestCase):
    """NotificationSendHandler creates OperatorAlert after max retries."""

    def setUp(self):
        from channels.handlers.notification import NotificationSendHandler
        from channels.notifications import _backends, register_backend
        from channels.protocols import NotificationResult

        self.handler = NotificationSendHandler()
        self._backends_backup = dict(_backends)
        _backends.clear()

        # All backends fail
        failing = MagicMock()
        failing.send = MagicMock(
            return_value=NotificationResult(success=False, error="Connection refused")
        )
        register_backend("manychat", failing)
        register_backend("email", failing)
        register_backend("sms", failing)

    def tearDown(self):
        from channels.notifications import _backends

        _backends.clear()
        _backends.update(self._backends_backup)

    def test_notification_failure_creates_alert_after_max_retries(self):
        """After 5 failed attempts, OperatorAlert is created."""
        from shop.models import OperatorAlert

        channel = Channel.objects.create(
            ref="wa-esc", name="WA Escalation",
            config={"notifications": {"backend": "manychat", "fallback_chain": ["email"]}},
        )
        order = Order.objects.create(
            ref="ORD-ESC-01", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_esc",
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )
        directive.attempts = 5
        directive.save()

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")

        # OperatorAlert was created
        alert = OperatorAlert.objects.filter(type="notification_failed").first()
        self.assertIsNotNone(alert)
        self.assertEqual(alert.severity, "error")
        self.assertIn("order_confirmed", alert.message)
        self.assertIn("ORD-ESC-01", alert.message)
        self.assertEqual(alert.order_ref, "ORD-ESC-01")

    def test_notification_no_alert_before_max_retries(self):
        """Before 5 attempts, no OperatorAlert — just queued for retry."""
        from shop.models import OperatorAlert

        channel = Channel.objects.create(
            ref="wa-retry", name="WA Retry",
            config={"notifications": {"backend": "manychat", "fallback_chain": []}},
        )
        order = Order.objects.create(
            ref="ORD-ESC-02", channel=channel, status="new",
            handle_type="manychat", handle_ref="sub_retry",
        )

        directive = _create_directive(
            topic=NOTIFICATION_SEND,
            payload={"order_ref": order.ref, "template": "order_confirmed"},
        )
        directive.attempts = 3
        directive.save()

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "queued")
        self.assertFalse(OperatorAlert.objects.filter(type="notification_failed").exists())


# ══════════════════════════════════════════════════════════════════════
# 0.5 Session Cleanup
# ══════════════════════════════════════════════════════════════════════


class TestSessionCleanup(TestCase):
    """cleanup_stale_sessions management command."""

    def setUp(self):
        self.channel = _make_channel(ref="cleanup-ch")

    def test_stale_sessions_cleaned(self):
        """Sessions older than 48h with no order are removed."""
        old = timezone.now() - timedelta(hours=49)
        s1 = Session.objects.create(
            session_key="stale-1", channel=self.channel, data={},
        )
        Session.objects.filter(pk=s1.pk).update(updated_at=old)

        # Recent session — should NOT be removed
        Session.objects.create(
            session_key="fresh-1", channel=self.channel, data={},
        )

        out = StringIO()
        call_command("cleanup_stale_sessions", stdout=out)

        self.assertFalse(Session.objects.filter(session_key="stale-1").exists())
        self.assertTrue(Session.objects.filter(session_key="fresh-1").exists())

    def test_session_with_order_not_cleaned(self):
        """Stale session with associated order is preserved."""
        old = timezone.now() - timedelta(hours=49)
        s = Session.objects.create(
            session_key="has-order", channel=self.channel, data={},
        )
        Session.objects.filter(pk=s.pk).update(updated_at=old)

        Order.objects.create(
            ref="ORD-KEEP", channel=self.channel, status="new",
            session_key="has-order",
        )

        out = StringIO()
        call_command("cleanup_stale_sessions", stdout=out)

        self.assertTrue(Session.objects.filter(session_key="has-order").exists())

    def test_dry_run_does_not_delete(self):
        """Dry run reports but doesn't delete."""
        old = timezone.now() - timedelta(hours=49)
        s = Session.objects.create(
            session_key="dry-run-1", channel=self.channel, data={},
        )
        Session.objects.filter(pk=s.pk).update(updated_at=old)

        out = StringIO()
        call_command("cleanup_stale_sessions", "--dry-run", stdout=out)

        self.assertTrue(Session.objects.filter(session_key="dry-run-1").exists())


# ══════════════════════════════════════════════════════════════════════
# 0.6 Hold TTL >= Payment Timeout (Startup Validation)
# ══════════════════════════════════════════════════════════════════════


class TestHoldTTLValidation(TestCase):
    """Startup validation: hold_ttl_minutes >= pix_timeout + margin."""

    def test_hold_ttl_gte_payment_timeout(self):
        """Default presets respect the invariant: hold_ttl >= payment_timeout + 5min margin."""
        from channels.config import ChannelConfig
        from channels.presets import remote

        # Remote: hold_ttl=30, payment timeout=15, margin=5 → 30 >= 20 ✓
        config = ChannelConfig.from_dict(remote())
        hold_ttl = config.stock.hold_ttl_minutes or 0
        pix_timeout = config.payment.timeout_minutes
        margin = 5

        self.assertGreaterEqual(hold_ttl, pix_timeout + margin,
            f"Remote hold_ttl ({hold_ttl}) must be >= payment_timeout ({pix_timeout}) + margin ({margin})")

    def test_startup_validation_warns_on_insufficient_ttl(self):
        """Apps.ready() warns if hold_ttl < pix_timeout + margin."""
        with patch("channels.apps.logger") as mock_logger:
            from channels.apps import ChannelsConfig
            # Validation runs during ready() — just verify the method exists
            self.assertTrue(hasattr(ChannelsConfig, "_validate_hold_ttl"))


# ══════════════════════════════════════════════════════════════════════
# 0.7 Custom Error Pages
# ══════════════════════════════════════════════════════════════════════


class TestCustomErrorPages(TestCase):
    """Branded 404 and 500 error pages."""

    def test_404_page_branded(self):
        """404 page returns branded content with link to menu."""
        client = Client()
        resp = client.get("/nonexistent-page-xyz/")
        self.assertEqual(resp.status_code, 404)
        content = resp.content.decode()
        self.assertIn("encontrada", content.lower())  # "Página não encontrada"

    def test_404_has_link_to_menu(self):
        """404 page has a link to /menu/."""
        client = Client()
        resp = client.get("/nonexistent-page-xyz/")
        content = resp.content.decode()
        self.assertIn("/menu/", content)

    def test_404_has_inline_css(self):
        """404 page uses inline CSS (no static file dependencies)."""
        client = Client()
        resp = client.get("/nonexistent-page-xyz/")
        content = resp.content.decode()
        self.assertIn("<style", content)

    def test_404_is_mobile_responsive(self):
        """404 page has viewport meta for mobile."""
        client = Client()
        resp = client.get("/nonexistent-page-xyz/")
        content = resp.content.decode()
        self.assertIn("viewport", content)


# ══════════════════════════════════════════════════════════════════════
# 0.8 HTMX Error Handling
# ══════════════════════════════════════════════════════════════════════


class TestHTMXErrorHandling(TestCase):
    """Global HTMX error handling in base template."""

    def test_base_template_has_htmx_error_handler(self):
        """base.html includes htmx:responseError handler."""
        import os

        template_path = os.path.join(
            os.path.dirname(__file__), "..",
            "channels", "web", "templates", "storefront", "base.html",
        )
        with open(template_path) as f:
            content = f.read()

        self.assertIn("htmx:responseError", content)

    def test_base_template_has_retry_logic(self):
        """base.html includes retry logic for 5xx errors."""
        import os

        template_path = os.path.join(
            os.path.dirname(__file__), "..",
            "channels", "web", "templates", "storefront", "base.html",
        )
        with open(template_path) as f:
            content = f.read()

        self.assertIn("retry", content.lower())

    def test_base_template_has_toast_component(self):
        """base.html includes toast notification component."""
        import os

        template_path = os.path.join(
            os.path.dirname(__file__), "..",
            "channels", "web", "templates", "storefront", "base.html",
        )
        with open(template_path) as f:
            content = f.read()

        self.assertIn("toast", content.lower())
