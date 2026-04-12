"""
Tests for shopman.lifecycle — declarative dispatch by ChannelConfig.

Uses mocking for services to test dispatch coordination in isolation.
All behavior is driven by ChannelConfig (payment.timing, fulfillment.timing,
confirmation.mode, stock.check_on_commit) — no Flow classes.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shopman.config import ChannelConfig
from shopman.lifecycle import dispatch, ensure_confirmable
from shopman.orderman.models import Directive, Order
from shopman.orderman.exceptions import InvalidTransition

# ── helpers ──


def _make_order(**overrides):
    """Create a mock Order with channel_ref."""
    order = MagicMock()
    order.ref = overrides.get("ref", "ORD-001")
    order.total_q = overrides.get("total_q", 5000)
    order.status = overrides.get("status", "new")
    order.data = overrides.get("data", {})
    order.snapshot = overrides.get("snapshot", {"items": [], "data": {}})
    order.channel_ref = overrides.get("channel_ref", "web")

    return order


def _config(**overrides):
    """Build a ChannelConfig with overrides."""
    kwargs = {}
    if "confirmation_mode" in overrides:
        kwargs["confirmation"] = ChannelConfig.Confirmation(
            mode=overrides["confirmation_mode"],
            timeout_minutes=overrides.get("confirmation_timeout", 5),
        )
    if "payment_timing" in overrides or "payment_method" in overrides:
        kwargs["payment"] = ChannelConfig.Payment(
            method=overrides.get("payment_method", "cash"),
            timing=overrides.get("payment_timing", "post_commit"),
        )
    if "fulfillment_timing" in overrides:
        kwargs["fulfillment"] = ChannelConfig.Fulfillment(
            timing=overrides["fulfillment_timing"],
        )
    if "check_on_commit" in overrides:
        kwargs["stock"] = ChannelConfig.Stock(
            check_on_commit=overrides["check_on_commit"],
        )
    return ChannelConfig(**kwargs)


# ── Dispatch basics ──


class TestDispatch:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_dispatch_calls_correct_phase(
        self, mock_stock, mock_customer, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(confirmation_mode="manual")
        order = _make_order()
        dispatch(order, "on_commit")
        mock_customer.ensure.assert_called_once_with(order)
        mock_stock.hold.assert_called_once_with(order)

    @patch("shopman.lifecycle.ChannelConfig")
    def test_dispatch_unknown_phase_logs_warning(self, mock_cc):
        mock_cc.for_channel.return_value = _config()
        order = _make_order()
        # Should not raise
        dispatch(order, "on_nonexistent_phase")

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    def test_dispatch_exception_propagates(self, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config()
        mock_notification.send.side_effect = RuntimeError("boom")
        order = _make_order()
        with pytest.raises(RuntimeError, match="boom"):
            dispatch(order, "on_dispatched")


class TestConfirmability:
    def test_ensure_confirmable_requires_positive_availability_decision(self):
        order = _make_order(data={})

        with pytest.raises(InvalidTransition, match="disponibilidade"):
            ensure_confirmable(order)

    def test_ensure_confirmable_accepts_positive_availability_decision(self):
        order = _make_order(
            data={"availability_decision": {"approved": True, "decisions": [{"sku": "PAO-001"}]}}
        )

        ensure_confirmable(order)


# ── on_commit ──


class TestOnCommit:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_calls_customer_ensure_and_stock_hold(
        self, mock_stock, mock_customer, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(confirmation_mode="manual")
        order = _make_order()
        dispatch(order, "on_commit")
        mock_customer.ensure.assert_called_once_with(order)
        mock_stock.hold.assert_called_once_with(order)

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_immediate_confirmation(
        self, mock_stock, mock_customer, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(confirmation_mode="immediate")
        order = _make_order()
        dispatch(order, "on_commit")
        order.transition_status.assert_called_once_with(
            Order.Status.CONFIRMED, actor="auto_confirm",
        )

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    @pytest.mark.django_db
    def test_optimistic_confirmation_creates_directive(
        self, mock_stock, mock_customer, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            confirmation_mode="optimistic", confirmation_timeout=5,
        )
        order = _make_order()
        dispatch(order, "on_commit")
        directive = Directive.objects.filter(topic="confirmation.timeout").first()
        assert directive is not None
        assert directive.payload["order_ref"] == "ORD-001"
        assert directive.payload["action"] == "confirm"

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_manual_confirmation_no_auto_action(
        self, mock_stock, mock_customer, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(confirmation_mode="manual")
        order = _make_order()
        dispatch(order, "on_commit")
        order.transition_status.assert_not_called()

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.payment")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_payment_at_commit(
        self, mock_stock, mock_customer, mock_loyalty, mock_payment, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            confirmation_mode="manual", payment_timing="at_commit",
        )
        order = _make_order()
        dispatch(order, "on_commit")
        mock_payment.initiate.assert_called_once_with(order)

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_no_payment_at_commit_when_post_commit(
        self, mock_stock, mock_customer, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            confirmation_mode="manual", payment_timing="post_commit",
        )
        order = _make_order()
        dispatch(order, "on_commit")
        # payment.initiate should NOT be called during commit for post_commit timing


class TestOnCommitAvailabilityCheck:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.availability")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_check_on_commit_rejects_unavailable(
        self, mock_stock, mock_customer, mock_availability, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            confirmation_mode="immediate", check_on_commit=True,
            payment_timing="external", payment_method="cash",
        )
        mock_availability.decide.return_value = {
            "approved": False, "reason_code": "insufficient_stock", "available_qty": 0,
        }
        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": 5}], "data": {}},
        )
        dispatch(order, "on_commit")

        order.transition_status.assert_called_once_with(
            Order.Status.CANCELLED, actor="auto_reject_unavailable",
        )
        mock_stock.hold.assert_not_called()

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.availability")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_check_on_commit_proceeds_when_available(
        self, mock_stock, mock_customer, mock_availability, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            confirmation_mode="immediate", check_on_commit=True,
            payment_timing="external", payment_method="cash",
        )
        mock_availability.decide.return_value = {
            "approved": True,
            "sku": "PAO-001",
            "requested_qty": 2,
            "available_qty": 2,
            "reason_code": None,
            "is_paused": False,
            "is_planned": False,
            "target_date": None,
            "failed_sku": None,
            "source": "stock.promise_decision",
        }
        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": 2}], "data": {}},
            data={"hold_ids": [{"sku": "PAO-001", "hold_id": "hold:1"}]},
        )
        dispatch(order, "on_commit")

        mock_stock.hold.assert_called_once_with(order)
        order.transition_status.assert_called_once_with(
            Order.Status.CONFIRMED, actor="auto_confirm",
        )

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_no_check_when_check_on_commit_false(
        self, mock_stock, mock_customer, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            confirmation_mode="manual",
        )
        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": 2}], "data": {}},
        )
        dispatch(order, "on_commit")
        # availability.check should NOT be called
        mock_stock.hold.assert_called_once_with(order)


# ── on_confirmed ──


class TestOnConfirmed:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.payment")
    def test_post_commit_initiates_payment(self, mock_payment, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config(
            payment_timing="post_commit", payment_method="pix",
        )
        order = _make_order()
        dispatch(order, "on_confirmed")
        mock_payment.initiate.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_confirmed")

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.payment")
    @patch("shopman.lifecycle.stock")
    def test_external_counter_fulfills_stock(
        self, mock_stock, mock_payment, mock_notification, mock_cc,
    ):
        """Counter payment (external timing) fulfills stock on confirmed."""
        mock_cc.for_channel.return_value = _config(
            payment_timing="external", payment_method="cash",
        )
        order = _make_order()
        dispatch(order, "on_confirmed")
        mock_payment.initiate.assert_not_called()
        mock_stock.fulfill.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_confirmed")

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.payment")
    @patch("shopman.lifecycle.stock")
    def test_external_marketplace_no_fulfill(
        self, mock_stock, mock_payment, mock_notification, mock_cc,
    ):
        """Marketplace payment (external timing, external method) does NOT fulfill on confirmed."""
        mock_cc.for_channel.return_value = _config(
            payment_timing="external", payment_method="external",
        )
        order = _make_order()
        dispatch(order, "on_confirmed")
        mock_payment.initiate.assert_not_called()
        mock_stock.fulfill.assert_not_called()
        mock_notification.send.assert_called_once_with(order, "order_confirmed")


# ── on_paid ──


class TestOnPaid:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.stock")
    def test_fulfills_stock_and_notifies(self, mock_stock, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config()
        order = _make_order(status="confirmed")
        dispatch(order, "on_paid")
        mock_stock.fulfill.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "payment_confirmed")

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle._create_alert")
    @patch("shopman.lifecycle.payment")
    def test_race_condition_cancelled_order_refunds(self, mock_payment, mock_alert, mock_cc):
        mock_cc.for_channel.return_value = _config()
        order = _make_order(status=Order.Status.CANCELLED)
        dispatch(order, "on_paid")
        mock_payment.refund.assert_called_once_with(order)
        mock_alert.assert_called_once_with(order, "payment_after_cancel")

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.stock")
    def test_race_condition_does_not_fulfill(self, mock_stock, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config()
        order = _make_order(status=Order.Status.CANCELLED)
        dispatch(order, "on_paid")
        mock_stock.fulfill.assert_not_called()
        mock_notification.send.assert_not_called()


# ── Other phases ──


class TestOnPreparing:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.services.kds.dispatch")
    def test_dispatches_kds_and_notifies(self, mock_kds_dispatch, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config()
        order = _make_order()
        dispatch(order, "on_preparing")
        mock_kds_dispatch.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_preparing")


class TestOnReady:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.fulfillment")
    def test_creates_fulfillment_and_notifies(self, mock_fulfillment, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config()
        order = _make_order()
        dispatch(order, "on_ready")
        mock_fulfillment.create.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_ready")

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.fulfillment")
    def test_no_fulfillment_when_external(self, mock_fulfillment, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config(fulfillment_timing="external")
        order = _make_order()
        dispatch(order, "on_ready")
        mock_fulfillment.create.assert_not_called()
        mock_notification.send.assert_called_once_with(order, "order_ready")


class TestOnCompleted:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.fiscal")
    @patch("shopman.lifecycle.loyalty")
    def test_earns_loyalty_and_emits_fiscal(self, mock_loyalty, mock_fiscal, mock_cc):
        mock_cc.for_channel.return_value = _config()
        order = _make_order()
        dispatch(order, "on_completed")
        mock_loyalty.earn.assert_called_once_with(order)
        mock_fiscal.emit.assert_called_once_with(order)


class TestOnCancelled:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.payment")
    @patch("shopman.lifecycle.stock")
    @patch("shopman.services.kds.cancel_tickets")
    def test_cancels_kds_releases_stock_refunds_and_notifies(
        self, mock_kds_cancel, mock_stock, mock_payment, mock_notification, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config()
        order = _make_order()
        dispatch(order, "on_cancelled")
        mock_kds_cancel.assert_called_once_with(order)
        mock_stock.release.assert_called_once_with(order)
        mock_payment.refund.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_cancelled")


class TestOnReturned:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.fiscal")
    @patch("shopman.lifecycle.payment")
    @patch("shopman.lifecycle.stock")
    def test_reverts_stock_refunds_cancels_fiscal_notifies(
        self, mock_stock, mock_payment, mock_fiscal, mock_notification, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config()
        order = _make_order()
        dispatch(order, "on_returned")
        mock_stock.revert.assert_called_once_with(order)
        mock_payment.refund.assert_called_once_with(order)
        mock_fiscal.cancel.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_returned")


class TestNotificationPhases:
    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    def test_on_dispatched_sends_notification(self, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config()
        order = _make_order()
        dispatch(order, "on_dispatched")
        mock_notification.send.assert_called_once_with(order, "order_dispatched")

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    def test_on_delivered_sends_notification(self, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config()
        order = _make_order()
        dispatch(order, "on_delivered")
        mock_notification.send.assert_called_once_with(order, "order_delivered")


# ── Channel-specific scenarios (config-driven) ──


class TestLocalChannelScenario:
    """Local channel: payment.timing=external, payment.method=counter,
    confirmation.mode=immediate, stock.check_on_commit=True."""

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.availability")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_commit_immediate_confirm(
        self, mock_stock, mock_customer, mock_availability, mock_loyalty, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            confirmation_mode="immediate",
            payment_timing="external", payment_method="cash",
            check_on_commit=True,
        )
        mock_availability.check.return_value = {"ok": True}
        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": 1}], "data": {}},
            data={"hold_ids": [{"sku": "PAO-001", "hold_id": "hold:1"}]},
        )
        dispatch(order, "on_commit")
        order.transition_status.assert_called_once_with(
            Order.Status.CONFIRMED, actor="auto_confirm",
        )

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.stock")
    def test_confirmed_fulfills_stock_no_payment(
        self, mock_stock, mock_notification, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            payment_timing="external", payment_method="cash",
        )
        order = _make_order()
        dispatch(order, "on_confirmed")
        mock_stock.fulfill.assert_called_once_with(order)


class TestRemoteChannelScenario:
    """Remote channel: payment.timing=post_commit, confirmation.mode=optimistic."""

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.payment")
    def test_confirmed_initiates_payment(self, mock_payment, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config(
            payment_timing="post_commit", payment_method="pix",
        )
        order = _make_order()
        dispatch(order, "on_confirmed")
        mock_payment.initiate.assert_called_once_with(order)

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.stock")
    def test_paid_fulfills_stock(self, mock_stock, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config(
            payment_timing="post_commit", payment_method="pix",
        )
        order = _make_order(status="confirmed")
        dispatch(order, "on_paid")
        mock_stock.fulfill.assert_called_once_with(order)


class TestMarketplaceChannelScenario:
    """Marketplace: payment.timing=external, payment.method=external,
    confirmation.mode=manual, stock.check_on_commit=True."""

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.availability")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_commit_manual_no_auto_action(
        self, mock_stock, mock_customer, mock_availability, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            confirmation_mode="manual",
            payment_timing="external", payment_method="external",
            check_on_commit=True,
        )
        mock_availability.check.return_value = {"ok": True}
        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": 2}], "data": {}},
            data={"hold_ids": [{"sku": "PAO-001", "hold_id": "hold:1"}]},
        )
        dispatch(order, "on_commit")
        mock_stock.hold.assert_called_once_with(order)
        order.transition_status.assert_not_called()

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.payment")
    @patch("shopman.lifecycle.stock")
    def test_confirmed_no_payment_no_fulfill(
        self, mock_stock, mock_payment, mock_notification, mock_cc,
    ):
        mock_cc.for_channel.return_value = _config(
            payment_timing="external", payment_method="external",
        )
        order = _make_order()
        dispatch(order, "on_confirmed")
        mock_payment.initiate.assert_not_called()
        mock_stock.fulfill.assert_not_called()

    @patch("shopman.lifecycle.ChannelConfig")
    @patch("shopman.lifecycle.notification")
    @patch("shopman.lifecycle.stock")
    def test_paid_fulfills_stock(self, mock_stock, mock_notification, mock_cc):
        mock_cc.for_channel.return_value = _config(
            payment_timing="external", payment_method="external",
        )
        order = _make_order(status="confirmed")
        dispatch(order, "on_paid")
        mock_stock.fulfill.assert_called_once_with(order)


# ── ChannelConfig integration ──


@pytest.mark.django_db
class TestChannelConfigIntegration:
    """Tests that dispatch() correctly reads the typed ChannelConfig
    cascade (channel ← shop ← defaults).
    """

    def _make_real_channel(self, ref="test-web"):
        from shopman.models import Channel
        return Channel.objects.create(ref=ref, name=f"Test {ref}")

    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_default_config_immediate_confirmation(
        self, mock_stock, mock_customer, mock_loyalty,
    ):
        """Default ChannelConfig has confirmation.mode=immediate → auto-confirms."""
        channel = self._make_real_channel()
        order = MagicMock()
        order.ref = "ORD-CFG-1"
        order.snapshot = {"items": []}
        order.data = {}
        order.channel_ref = channel.ref

        dispatch(order, "on_commit")
        order.transition_status.assert_called_once_with(
            Order.Status.CONFIRMED, actor="auto_confirm",
        )

    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_optimistic_uses_timeout_minutes_from_schema(
        self, mock_stock, mock_customer, mock_loyalty,
    ):
        from shopman.models import Shop
        Shop.objects.get_or_create(
            name="Test Shop",
            defaults={"defaults": {"confirmation": {"mode": "optimistic", "timeout_minutes": 7}}},
        )
        shop = Shop.load()
        shop.defaults = {"confirmation": {"mode": "optimistic", "timeout_minutes": 7}}
        shop.save()

        channel = self._make_real_channel()
        order = MagicMock()
        order.ref = "ORD-CFG-2"
        order.snapshot = {"items": []}
        order.data = {}
        order.channel_ref = channel.ref

        dispatch(order, "on_commit")

        directive = Directive.objects.filter(
            topic="confirmation.timeout", payload__order_ref="ORD-CFG-2",
        ).first()
        assert directive is not None
        from datetime import timedelta  # noqa: I001

        from django.utils import timezone
        delta = directive.available_at - timezone.now()
        assert timedelta(minutes=6) < delta < timedelta(minutes=8)

    @patch("shopman.lifecycle.loyalty")
    @patch("shopman.lifecycle.customer")
    @patch("shopman.lifecycle.stock")
    def test_shop_defaults_manual_no_auto_action(
        self, mock_stock, mock_customer, mock_loyalty,
    ):
        from shopman.models import Shop
        shop = Shop.load()
        shop.defaults = {"confirmation": {"mode": "manual"}}
        shop.save()

        channel = self._make_real_channel()
        order = MagicMock()
        order.ref = "ORD-CFG-4"
        order.snapshot = {"items": []}
        order.data = {}
        order.channel_ref = channel.ref

        dispatch(order, "on_commit")
        order.transition_status.assert_not_called()
