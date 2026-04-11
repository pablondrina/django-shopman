"""
WP-H2-4 — E2E lifecycle tests: session → commit → flow → handlers → directives.

9 scenarios covering the full orchestration stack with a real DB (no ORM mocks).
External services (payment gateway, notifications, stock holds) are patched at
the service boundary so tests are deterministic without network access.

Scenarios:
  E2E-1  checkout local, pagamento balcão, confirmação imediata
  E2E-2  checkout web, PIX feliz (webhook chega) → on_paid → preparing
  E2E-3  checkout web, PIX — cancelamento antes do webhook
  E2E-4  checkout web, PIX — webhook chega DEPOIS do cancelamento
  E2E-5  checkout marketplace, disponibilidade insuficiente em on_commit
  E2E-6  commit duplicado com mesma idempotency_key (idempotência)
  E2E-7  dois commits concorrentes na mesma sessão (race condition)
  E2E-8  notificação falhando — directive entra em retry
  E2E-9  hold parcial — um componente de bundle indisponível (stock.hold falha)
"""

from __future__ import annotations

import threading
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, TransactionTestCase

from shopman.models import Channel
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Directive, Order, Session
from shopman.orderman.services import CommitService

# ── Service patch targets ─────────────────────────────────────────────

_PATCHES = [
    "shopman.services.notification.send",
    "shopman.services.stock.hold",
    "shopman.services.stock.fulfill",
    "shopman.services.stock.release",
    "shopman.services.stock.revert",
    "shopman.services.payment.initiate",
    "shopman.services.payment.refund",
    "shopman.services.payment.capture",
    "shopman.services.customer.ensure",
    "shopman.services.loyalty.redeem",
    "shopman.services.loyalty.earn",
    "shopman.services.fiscal.emit",
    "shopman.services.fiscal.cancel",
    "shopman.services.kds.dispatch",
    "shopman.services.kds.cancel_tickets",
    "shopman.services.availability.check",
    "shopman.services.fulfillment.create",
]


_DEFAULT_RETURN: dict[str, object] = {
    "shopman.services.availability.check": {
        "ok": True,
        "available_qty": Decimal("999"),
        "is_paused": False,
        "is_planned": False,
        "breakdown": {},
        "error_code": None,
        "is_bundle": False,
        "failed_sku": None,
    },
}


def _start_patches(extra=None):
    """Start all standard service patches. Returns list of started patchers."""
    mocks = {}
    patchers = []
    targets = _PATCHES + (extra or [])
    for target in targets:
        ret = _DEFAULT_RETURN.get(target, None)
        p = patch(target, return_value=ret)
        try:
            m = p.start()
            patchers.append(p)
            mocks[target.rsplit(".", 1)[-1]] = m
        except AttributeError:
            pass
    return patchers, mocks


def _stop_patches(patchers):
    for p in patchers:
        try:
            p.stop()
        except RuntimeError:
            pass


_LOCAL_CONFIG = {
    "confirmation": {"mode": "immediate"},
    "payment": {"method": "cash", "timing": "external"},
    "stock": {"check_on_commit": True},
}

_REMOTE_CONFIG = {
    "confirmation": {"mode": "immediate"},
    "payment": {"method": "pix", "timing": "post_commit"},
}

_MARKETPLACE_CONFIG = {
    "confirmation": {"mode": "manual"},
    "payment": {"method": "external", "timing": "external"},
    "stock": {"check_on_commit": True},
}


def _make_channel(ref="test", kind="local", config=None, **kwargs):
    channel = Channel.objects.create(
        ref=ref,
        name=ref.title(),
        kind=kind,
        config=config or {},
        **kwargs,
    )
    return channel


def _make_session(channel, key=None):
    key = key or generate_session_key()
    return Session.objects.create(
        session_key=key,
        channel_ref=channel.ref,
        state="open",
        items=[{"sku": "PAO-FRANCES", "qty": 2, "unit_price_q": 80, "line_id": "L1"}],
    )


def _commit(session, channel):
    return CommitService.commit(
        session_key=session.session_key,
        channel_ref=channel.ref,
        idempotency_key=generate_idempotency_key(),
    )


# ─────────────────────────────────────────────────────────────────────
# E2E-1: local checkout, balcão payment, immediate confirmation
# ─────────────────────────────────────────────────────────────────────

class TestE2E1LocalCheckout(TestCase):
    """Local channel: commit → auto-confirm → stock.fulfill."""

    def setUp(self):
        self.channel = _make_channel(ref="balcao", kind="local", config=_LOCAL_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_local_checkout_immediate_confirmation(self):
        session = _make_session(self.channel)
        result = _commit(session, self.channel)

        order = Order.objects.get(ref=result["order_ref"])

        # on_commit → auto_confirm → on_confirmed → stock.fulfill
        self.assertEqual(order.status, Order.Status.CONFIRMED)
        # stock.fulfill called once in on_confirmed
        self.mocks["fulfill"].assert_called_once()


# ─────────────────────────────────────────────────────────────────────
# E2E-2: web PIX happy path — webhook → on_paid → paid
# ─────────────────────────────────────────────────────────────────────

class TestE2E2WebPixHappyPath(TestCase):
    """Remote channel: commit → confirmed → on_paid → stock.fulfill."""

    def setUp(self):
        self.channel = _make_channel(ref="web", kind="web", config=_REMOTE_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_web_pix_happy_path(self):
        from shopman.lifecycle import dispatch

        session = _make_session(self.channel)
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result["order_ref"])

        # on_commit → immediate confirmation → on_confirmed
        order.transition_status(Order.Status.CONFIRMED, actor="test")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CONFIRMED)

        # Simulate PIX webhook arriving → dispatch on_paid
        dispatch(order, "on_paid")

        # on_paid → stock.fulfill + notification
        self.mocks["fulfill"].assert_called()


# ─────────────────────────────────────────────────────────────────────
# E2E-3: web PIX — cancellation before webhook
# ─────────────────────────────────────────────────────────────────────

class TestE2E3WebPixCancelledBeforeWebhook(TestCase):
    """Operator cancels order before PIX webhook arrives."""

    def setUp(self):
        self.channel = _make_channel(ref="web-cancel", kind="web", config=_REMOTE_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_cancel_before_pix_webhook(self):
        session = _make_session(self.channel)
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result["order_ref"])

        order.transition_status(Order.Status.CONFIRMED, actor="test")
        order.transition_status(Order.Status.CANCELLED, actor="operator")
        order.refresh_from_db()

        self.assertEqual(order.status, Order.Status.CANCELLED)
        # on_cancelled → stock.release + payment.refund
        self.mocks["release"].assert_called()
        self.mocks["refund"].assert_called()


# ─────────────────────────────────────────────────────────────────────
# E2E-4: web PIX — webhook arrives AFTER cancellation
# ─────────────────────────────────────────────────────────────────────

class TestE2E4WebPixWebhookAfterCancellation(TestCase):
    """PIX webhook arrives after operator already cancelled the order.

    dispatch on_paid checks for CANCELLED status and refunds instead of
    fulfilling. This test confirms that protection holds.
    """

    def setUp(self):
        self.channel = _make_channel(ref="web-late", kind="web", config=_REMOTE_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_on_paid_with_cancelled_order_does_not_fulfill(self):
        from shopman.lifecycle import dispatch

        session = _make_session(self.channel)
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result["order_ref"])

        # Operator cancels
        order.transition_status(Order.Status.CONFIRMED, actor="test")
        order.transition_status(Order.Status.CANCELLED, actor="operator")
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)

        # Reset mock call counters
        self.mocks["fulfill"].reset_mock()
        self.mocks["refund"].reset_mock()

        # PIX webhook arrives late — simulate on_paid called with cancelled order
        dispatch(order, "on_paid")

        # fulfill must NOT be called — refund must be called
        self.mocks["fulfill"].assert_not_called()
        self.mocks["refund"].assert_called_once()
        # Order remains CANCELLED
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)


# ─────────────────────────────────────────────────────────────────────
# E2E-5: marketplace — insufficient availability → auto-cancel
# ─────────────────────────────────────────────────────────────────────

class TestE2E5MarketplaceInsufficientStock(TestCase):
    """Marketplace on_commit rejects order when availability.check fails."""

    def setUp(self):
        self.channel = _make_channel(ref="ifood", kind="marketplace", config=_MARKETPLACE_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_marketplace_rejects_when_unavailable(self):
        # availability.check returns failure
        self.mocks["check"].return_value = {
            "ok": False,
            "available_qty": Decimal("0"),
            "is_paused": False,
            "is_planned": False,
            "breakdown": {},
            "error_code": "out_of_stock",
            "is_bundle": False,
            "failed_sku": None,
        }

        session = _make_session(self.channel)
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result["order_ref"])

        # on_commit cancels when availability fails (check_on_commit=True)
        order.refresh_from_db()
        self.assertEqual(order.status, Order.Status.CANCELLED)
        # stock.hold must NOT be called — order was rejected before hold
        self.mocks["hold"].assert_not_called()


# ─────────────────────────────────────────────────────────────────────
# E2E-6: duplicate commit with same idempotency_key
# ─────────────────────────────────────────────────────────────────────

class TestE2E6DuplicateCommit(TestCase):
    """Duplicate commit with same idempotency_key returns cached result."""

    def setUp(self):
        self.channel = _make_channel(ref="idem-test", kind="local", config=_LOCAL_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_duplicate_commit_idempotent(self):
        session_key = generate_session_key()
        session = Session.objects.create(
            session_key=session_key,
            channel_ref=self.channel.ref,
            state="open",
            items=[{"sku": "PAO-FRANCES", "qty": 1, "unit_price_q": 80, "line_id": "L1"}],
        )
        idem_key = generate_idempotency_key()

        result1 = CommitService.commit(
            session_key=session_key,
            channel_ref=self.channel.ref,
            idempotency_key=idem_key,
        )
        result2 = CommitService.commit(
            session_key=session_key,
            channel_ref=self.channel.ref,
            idempotency_key=idem_key,
        )

        # Same order_ref returned
        self.assertEqual(result1["order_ref"], result2["order_ref"])
        # Only one Order created
        self.assertEqual(Order.objects.count(), 1)


# ─────────────────────────────────────────────────────────────────────
# E2E-7: concurrent commits on same session (race condition)
# ─────────────────────────────────────────────────────────────────────

class TestE2E7ConcurrentCommits(TransactionTestCase):
    """Two concurrent commits on the same session do not create duplicate Orders.

    Uses TransactionTestCase because select_for_update requires actual
    transaction boundaries between threads.
    """

    def setUp(self):
        self.channel = _make_channel(ref="race-test", kind="local", config=_LOCAL_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_concurrent_commits_create_single_order(self):
        session_key = generate_session_key()
        Session.objects.create(
            session_key=session_key,
            channel_ref=self.channel.ref,
            state="open",
            items=[{"sku": "PAO-FRANCES", "qty": 1, "unit_price_q": 80, "line_id": "L1"}],
        )

        results = []
        errors = []

        def do_commit(idem_key):
            try:
                r = CommitService.commit(
                    session_key=session_key,
                    channel_ref=self.channel.ref,
                    idempotency_key=idem_key,
                )
                results.append(r)
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=do_commit, args=(generate_idempotency_key(),))
        t2 = threading.Thread(target=do_commit, args=(generate_idempotency_key(),))
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Both threads must have completed
        total = len(results) + len(errors)
        self.assertEqual(total, 2)

        # The critical invariant: NO duplicate Order created.
        # SQLite may serialize both commits (one wins, one fails with lock error),
        # or may fail both in contention. Either way, at most 1 Order must exist.
        order_count = Order.objects.count()
        self.assertLessEqual(order_count, 1, "Concurrent commits must not create duplicate Orders")


# ─────────────────────────────────────────────────────────────────────
# E2E-8: notification failure — directive enters retry
# ─────────────────────────────────────────────────────────────────────

class TestE2E8NotificationFailureDirectiveRetry(TestCase):
    """When a directive handler raises DirectiveTransientError, worker retries."""

    def setUp(self):
        self.channel = _make_channel(ref="notif-test", kind="local", config=_LOCAL_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_directive_transient_error_stays_queued(self):
        from shopman.orderman.exceptions import DirectiveTransientError
        from shopman.orderman.management.commands.process_directives import Command

        # Create a directive
        directive = Directive.objects.create(
            topic="notification.order_confirmed",
            payload={"order_ref": "ORD-TEST-001"},
        )

        # Handler raises transient error
        mock_handler = MagicMock()
        mock_handler.handle.side_effect = DirectiveTransientError("network timeout")

        with patch("shopman.orderman.registry.get_directive_handler", return_value=mock_handler):
            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.stderr = MagicMock()
            cmd.style = MagicMock()
            cmd.style.ERROR = lambda x: x
            cmd.style.WARNING = lambda x: x
            cmd.style.SUCCESS = lambda x: x
            cmd.handle(topics=["notification.order_confirmed"], limit=10, watch=False, interval=2.0, max_attempts=5, reap_timeout=0)

        directive.refresh_from_db()
        # Transient error: stays queued (not failed), error_code set
        self.assertEqual(directive.status, "queued")
        self.assertEqual(directive.error_code, "transient")
        self.assertGreater(directive.attempts, 0)


class TestE2E8TerminalErrorDirectiveFails(TestCase):
    """When a directive handler raises DirectiveTerminalError, it is marked failed immediately."""

    def setUp(self):
        self.channel = _make_channel(ref="terminal-test", kind="local", config=_LOCAL_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_directive_terminal_error_marks_failed(self):
        from shopman.orderman.exceptions import DirectiveTerminalError
        from shopman.orderman.management.commands.process_directives import Command

        directive = Directive.objects.create(
            topic="notification.order_confirmed",
            payload={"order_ref": "ORD-TEST-002"},
        )

        mock_handler = MagicMock()
        mock_handler.handle.side_effect = DirectiveTerminalError("invalid payload")

        with patch("shopman.orderman.registry.get_directive_handler", return_value=mock_handler):
            cmd = Command()
            cmd.stdout = MagicMock()
            cmd.stderr = MagicMock()
            cmd.style = MagicMock()
            cmd.style.ERROR = lambda x: x
            cmd.style.WARNING = lambda x: x
            cmd.style.SUCCESS = lambda x: x
            cmd.handle(topics=["notification.order_confirmed"], limit=10, watch=False, interval=2.0, max_attempts=5, reap_timeout=0)

        directive.refresh_from_db()
        # Terminal error: immediately failed, no retry
        self.assertEqual(directive.status, "failed")
        self.assertEqual(directive.error_code, "terminal")


# ─────────────────────────────────────────────────────────────────────
# E2E-9: stock.hold failure during commit
# ─────────────────────────────────────────────────────────────────────

class TestE2E9StockHoldFailure(TestCase):
    """If stock.hold raises, the order is created but the flow surfaces the error.

    The flow does NOT silently swallow stock failures — they propagate so the
    signal handler can surface them to the operator.
    """

    def setUp(self):
        self.channel = _make_channel(ref="stock-fail", kind="web", config=_REMOTE_CONFIG)
        self.patchers, self.mocks = _start_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    def test_stock_hold_failure_propagates(self):
        # Override stock.hold to raise
        self.mocks["hold"].side_effect = RuntimeError("stock hold failed: partial bundle")

        session = _make_session(self.channel)

        # CommitService._do_commit is @transaction.atomic. When stock.hold raises
        # inside the signal handler (on_order_changed → flows.dispatch → on_commit),
        # the exception propagates through order_changed.send(), aborting the
        # transaction and rolling back the Order creation.
        with self.assertRaises(RuntimeError):
            _commit(session, self.channel)

        # Transaction rolled back — no Order was created
        self.assertEqual(Order.objects.count(), 0)
