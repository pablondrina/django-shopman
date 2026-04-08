"""
Tests for shopman.flows — Flow hierarchy, dispatch, and lifecycle phases.

Uses mocking for services to test flow coordination in isolation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from shopman.flows import (
    BaseFlow,
    IFoodFlow,
    LocalFlow,
    ManychatFlow,
    MarketplaceFlow,
    PosFlow,
    RemoteFlow,
    TotemFlow,
    WebFlow,
    WhatsAppFlow,
    _registry,
    dispatch,
    get_flow,
)
from shopman.ordering.models import Directive, Order

# ── helpers ──


def _make_order(**overrides):
    """Create a mock Order with channel config."""
    order = MagicMock()
    order.ref = overrides.get("ref", "ORD-001")
    order.total_q = overrides.get("total_q", 5000)
    order.status = overrides.get("status", "new")
    order.data = overrides.get("data", {})
    order.snapshot = overrides.get("snapshot", {"items": [], "data": {}})

    channel = MagicMock()
    channel.ref = overrides.get("channel_ref", "web")
    channel.name = "Web"
    channel.config = overrides.get("channel_config", {})
    order.channel = channel

    return order


# ── Registry and dispatch ──


class TestRegistry:
    def test_all_flows_registered(self):
        expected = {
            "base", "local", "pos", "totem",
            "remote", "web", "whatsapp", "manychat",
            "marketplace", "ifood",
        }
        assert expected == set(_registry.keys())

    def test_flow_classes_correct(self):
        assert _registry["base"] is BaseFlow
        assert _registry["local"] is LocalFlow
        assert _registry["pos"] is PosFlow
        assert _registry["totem"] is TotemFlow
        assert _registry["remote"] is RemoteFlow
        assert _registry["web"] is WebFlow
        assert _registry["whatsapp"] is WhatsAppFlow
        assert _registry["manychat"] is ManychatFlow
        assert _registry["marketplace"] is MarketplaceFlow
        assert _registry["ifood"] is IFoodFlow


class TestGetFlow:
    def test_resolves_from_channel_config(self):
        order = _make_order(channel_config={"flow": "web"})
        flow = get_flow(order)
        assert isinstance(flow, WebFlow)

    def test_resolves_local(self):
        order = _make_order(channel_config={"flow": "local"})
        flow = get_flow(order)
        assert isinstance(flow, LocalFlow)

    def test_resolves_marketplace(self):
        order = _make_order(channel_config={"flow": "marketplace"})
        flow = get_flow(order)
        assert isinstance(flow, MarketplaceFlow)

    def test_defaults_to_base(self):
        order = _make_order(channel_config={})
        flow = get_flow(order)
        assert isinstance(flow, BaseFlow)

    def test_unknown_flow_defaults_to_base(self):
        order = _make_order(channel_config={"flow": "nonexistent"})
        flow = get_flow(order)
        assert isinstance(flow, BaseFlow)


class TestDispatch:
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_dispatch_calls_correct_phase(self, mock_stock, mock_customer):
        order = _make_order(channel_config={"flow": "base", "confirmation_mode": "pessimistic"})
        dispatch(order, "on_commit")
        mock_customer.ensure.assert_called_once_with(order)
        mock_stock.hold.assert_called_once_with(order)

    def test_dispatch_unknown_phase_logs_warning(self):
        order = _make_order(channel_config={"flow": "base"})
        # Should not raise
        dispatch(order, "on_nonexistent_phase")

    @patch("shopman.flows.notification")
    def test_dispatch_exception_does_not_propagate(self, mock_notification):
        mock_notification.send.side_effect = RuntimeError("boom")
        order = _make_order(channel_config={"flow": "base"})
        # Should not raise — dispatch catches exceptions
        dispatch(order, "on_dispatched")


# ── Hierarchy ──


class TestHierarchy:
    def test_local_inherits_base(self):
        assert issubclass(LocalFlow, BaseFlow)

    def test_pos_inherits_local(self):
        assert issubclass(PosFlow, LocalFlow)

    def test_totem_inherits_local(self):
        assert issubclass(TotemFlow, LocalFlow)

    def test_remote_inherits_base(self):
        assert issubclass(RemoteFlow, BaseFlow)

    def test_web_inherits_remote(self):
        assert issubclass(WebFlow, RemoteFlow)

    def test_whatsapp_inherits_remote(self):
        assert issubclass(WhatsAppFlow, RemoteFlow)

    def test_manychat_inherits_remote(self):
        assert issubclass(ManychatFlow, RemoteFlow)

    def test_marketplace_inherits_base(self):
        assert issubclass(MarketplaceFlow, BaseFlow)

    def test_ifood_inherits_marketplace(self):
        assert issubclass(IFoodFlow, MarketplaceFlow)


# ── BaseFlow phases ──


class TestBaseFlowOnCommit:
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_calls_customer_ensure_and_stock_hold(self, mock_stock, mock_customer):
        order = _make_order(channel_config={"confirmation_mode": "pessimistic"})
        BaseFlow().on_commit(order)
        mock_customer.ensure.assert_called_once_with(order)
        mock_stock.hold.assert_called_once_with(order)

    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_immediate_confirmation(self, mock_stock, mock_customer):
        order = _make_order(channel_config={"confirmation_mode": "immediate"})
        BaseFlow().on_commit(order)
        order.transition_status.assert_called_once_with(
            Order.Status.CONFIRMED, actor="auto_confirm",
        )

    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    @pytest.mark.django_db
    def test_optimistic_confirmation_creates_directive(self, mock_stock, mock_customer):
        order = _make_order(channel_config={
            "confirmation_mode": "optimistic",
            "confirmation_timeout": 300,
        })
        BaseFlow().on_commit(order)
        directive = Directive.objects.filter(topic="confirmation.timeout").first()
        assert directive is not None
        assert directive.payload["order_ref"] == "ORD-001"
        assert directive.payload["action"] == "confirm"

    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_pessimistic_confirmation_no_auto_action(self, mock_stock, mock_customer):
        order = _make_order(channel_config={"confirmation_mode": "pessimistic"})
        BaseFlow().on_commit(order)
        order.transition_status.assert_not_called()


class TestBaseFlowOnConfirmed:
    @patch("shopman.flows.notification")
    @patch("shopman.flows.payment")
    def test_initiates_payment_and_notifies(self, mock_payment, mock_notification):
        order = _make_order()
        BaseFlow().on_confirmed(order)
        mock_payment.initiate.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_confirmed")


class TestBaseFlowOnPaid:
    @patch("shopman.flows.notification")
    @patch("shopman.flows.stock")
    def test_fulfills_stock_and_notifies(self, mock_stock, mock_notification):
        order = _make_order(status="confirmed")
        BaseFlow().on_paid(order)
        mock_stock.fulfill.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "payment_confirmed")

    @patch("shopman.flows._create_alert")
    @patch("shopman.flows.payment")
    def test_race_condition_cancelled_order_refunds(self, mock_payment, mock_alert):
        order = _make_order(status=Order.Status.CANCELLED)
        BaseFlow().on_paid(order)
        mock_payment.refund.assert_called_once_with(order)
        mock_alert.assert_called_once_with(order, "payment_after_cancel")

    @patch("shopman.flows.notification")
    @patch("shopman.flows.stock")
    def test_race_condition_does_not_fulfill(self, mock_stock, mock_notification):
        order = _make_order(status=Order.Status.CANCELLED)
        BaseFlow().on_paid(order)
        mock_stock.fulfill.assert_not_called()
        mock_notification.send.assert_not_called()


class TestBaseFlowOnPreparing:
    @patch("shopman.flows.notification")
    @patch("shopman.flows.kds")
    def test_dispatches_kds_and_notifies(self, mock_kds, mock_notification):
        order = _make_order()
        BaseFlow().on_preparing(order)
        mock_kds.dispatch.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_preparing")


class TestBaseFlowOnReady:
    @patch("shopman.flows.notification")
    @patch("shopman.flows.fulfillment")
    def test_creates_fulfillment_and_notifies(self, mock_fulfillment, mock_notification):
        order = _make_order()
        BaseFlow().on_ready(order)
        mock_fulfillment.create.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_ready")


class TestBaseFlowOnCompleted:
    @patch("shopman.flows.fiscal")
    @patch("shopman.flows.loyalty")
    def test_earns_loyalty_and_emits_fiscal(self, mock_loyalty, mock_fiscal):
        order = _make_order()
        BaseFlow().on_completed(order)
        mock_loyalty.earn.assert_called_once_with(order)
        mock_fiscal.emit.assert_called_once_with(order)


class TestBaseFlowOnCancelled:
    @patch("shopman.flows.notification")
    @patch("shopman.flows.payment")
    @patch("shopman.flows.stock")
    @patch("shopman.flows.kds")
    def test_cancels_kds_tickets_releases_stock_refunds_and_notifies(
        self, mock_kds, mock_stock, mock_payment, mock_notification
    ):
        order = _make_order()
        BaseFlow().on_cancelled(order)
        mock_kds.cancel_tickets.assert_called_once_with(order)
        mock_stock.release.assert_called_once_with(order)
        mock_payment.refund.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_cancelled")


class TestBaseFlowOnReturned:
    @patch("shopman.flows.notification")
    @patch("shopman.flows.fiscal")
    @patch("shopman.flows.payment")
    @patch("shopman.flows.stock")
    def test_reverts_stock_refunds_cancels_fiscal_notifies(
        self, mock_stock, mock_payment, mock_fiscal, mock_notification,
    ):
        order = _make_order()
        BaseFlow().on_returned(order)
        mock_stock.revert.assert_called_once_with(order)
        mock_payment.refund.assert_called_once_with(order)
        mock_fiscal.cancel.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_returned")


# ── LocalFlow ──


class TestLocalFlow:
    @patch("shopman.flows.availability")
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_on_commit_immediate_confirmation(self, mock_stock, mock_customer, mock_availability):
        mock_availability.check.return_value = {"ok": True}
        order = _make_order(
            channel_config={"flow": "local"},
            snapshot={"items": [{"sku": "PAO-001", "qty": 1}], "data": {}},
        )
        LocalFlow().on_commit(order)
        order.transition_status.assert_called_once_with(
            Order.Status.CONFIRMED, actor="auto_confirm",
        )

    @patch("shopman.flows._create_alert")
    @patch("shopman.flows.availability")
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_on_commit_rejects_when_item_unavailable(
        self, mock_stock, mock_customer, mock_availability, mock_alert,
    ):
        """LocalFlow.on_commit cancels order when any item fails availability check."""
        mock_availability.check.return_value = {
            "ok": False,
            "error_code": "insufficient_stock",
            "available_qty": 0,
        }
        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": 5}], "data": {}},
        )

        LocalFlow().on_commit(order)

        # Alert created, order cancelled, stock.hold NOT called
        mock_alert.assert_called_once_with(order, "pos_rejected_unavailable")
        order.transition_status.assert_called_once_with(
            Order.Status.CANCELLED, actor="auto_reject_unavailable",
        )
        mock_stock.hold.assert_not_called()

    @patch("shopman.flows.availability")
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_on_commit_proceeds_when_all_available(
        self, mock_stock, mock_customer, mock_availability,
    ):
        """LocalFlow.on_commit proceeds to stock.hold when all items are available."""
        mock_availability.check.return_value = {"ok": True}
        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": 2}], "data": {}},
        )

        LocalFlow().on_commit(order)

        mock_stock.hold.assert_called_once_with(order)
        order.transition_status.assert_called_once_with(
            Order.Status.CONFIRMED, actor="auto_confirm",
        )

    @patch("shopman.flows.notification")
    def test_on_confirmed_no_payment(self, mock_notification):
        order = _make_order()
        LocalFlow().on_confirmed(order)
        mock_notification.send.assert_called_once_with(order, "order_confirmed")

    def test_on_paid_is_noop(self):
        order = _make_order()
        # Should not raise
        LocalFlow().on_paid(order)

    @patch("shopman.flows.notification")
    @patch("shopman.flows.payment")
    @patch("shopman.flows.stock")
    @patch("shopman.flows.kds")
    def test_on_cancelled_inherits_base(self, mock_kds, mock_stock, mock_payment, mock_notification):
        order = _make_order()
        LocalFlow().on_cancelled(order)
        mock_kds.cancel_tickets.assert_called_once_with(order)
        mock_stock.release.assert_called_once_with(order)
        mock_payment.refund.assert_called_once_with(order)
        mock_notification.send.assert_called_once_with(order, "order_cancelled")


# ── RemoteFlow ──


class TestRemoteFlow:
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_inherits_base_on_commit(self, mock_stock, mock_customer):
        order = _make_order(channel_config={"confirmation_mode": "pessimistic"})
        RemoteFlow().on_commit(order)
        mock_customer.ensure.assert_called_once_with(order)
        mock_stock.hold.assert_called_once_with(order)

    @patch("shopman.flows.notification")
    @patch("shopman.flows.payment")
    def test_inherits_base_on_confirmed(self, mock_payment, mock_notification):
        order = _make_order()
        RemoteFlow().on_confirmed(order)
        mock_payment.initiate.assert_called_once_with(order)


# ── MarketplaceFlow ──


class TestMarketplaceFlow:
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_on_commit_pessimistic_no_auto_action(self, mock_stock, mock_customer):
        order = _make_order(channel_config={"flow": "marketplace"})
        MarketplaceFlow().on_commit(order)
        mock_customer.ensure.assert_called_once_with(order)
        mock_stock.hold.assert_called_once_with(order)
        # Pessimistic: no transition, no directive
        order.transition_status.assert_not_called()

    @patch("shopman.flows._create_alert")
    @patch("shopman.flows.availability")
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_on_commit_rejects_when_item_not_in_listing(
        self, mock_stock, mock_customer, mock_availability, mock_alert,
    ):
        """Marketplace rejects pre-emptively when availability.check fails.

        Per-item check is honored BEFORE stock.hold; failure (e.g.
        not_in_listing, paused, insufficient_stock) cancels the order.
        """
        order = _make_order(
            channel_config={"flow": "marketplace"},
            snapshot={"items": [{"sku": "PAO-001", "qty": "2"}], "data": {}},
        )
        mock_availability.check.return_value = {
            "ok": False,
            "is_paused": False,
            "available_qty": 0,
            "error_code": "not_in_listing",
        }

        MarketplaceFlow().on_commit(order)

        mock_availability.check.assert_called_once_with(
            "PAO-001", "2", channel_ref="web",
        )
        mock_stock.hold.assert_not_called()
        mock_alert.assert_called_once_with(order, "marketplace_rejected_unavailable")
        order.transition_status.assert_called_once_with(
            Order.Status.CANCELLED, actor="auto_reject_unavailable",
        )

    @patch("shopman.flows._create_alert")
    @patch("shopman.flows.availability")
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_on_commit_proceeds_when_all_items_available(
        self, mock_stock, mock_customer, mock_availability, mock_alert,
    ):
        order = _make_order(
            channel_config={"flow": "marketplace"},
            snapshot={"items": [{"sku": "PAO-001", "qty": "2"}], "data": {}},
            data={"hold_ids": [{"sku": "PAO-001", "hold_id": "hold:1"}]},
        )
        mock_availability.check.return_value = {"ok": True, "available_qty": 100}

        MarketplaceFlow().on_commit(order)

        mock_stock.hold.assert_called_once_with(order)
        mock_alert.assert_not_called()
        order.transition_status.assert_not_called()

    @patch("shopman.flows.notification")
    def test_on_confirmed_no_payment_initiate(self, mock_notification):
        order = _make_order()
        MarketplaceFlow().on_confirmed(order)
        mock_notification.send.assert_called_once_with(order, "order_confirmed")

    @patch("shopman.flows.notification")
    @patch("shopman.flows.stock")
    def test_on_paid_fulfills_stock(self, mock_stock, mock_notification):
        order = _make_order(status="confirmed")
        MarketplaceFlow().on_paid(order)
        mock_stock.fulfill.assert_called_once_with(order)

    @patch("shopman.flows._create_alert")
    def test_on_paid_cancelled_creates_alert(self, mock_alert):
        order = _make_order(status=Order.Status.CANCELLED)
        MarketplaceFlow().on_paid(order)
        mock_alert.assert_called_once_with(order, "payment_after_cancel")


# ── Signal-driven dispatch ──


class TestSignalDispatch:
    @patch("shopman.flows.customer")
    @patch("shopman.flows.stock")
    def test_created_event_triggers_on_commit(self, mock_stock, mock_customer):
        order = _make_order(channel_config={"confirmation_mode": "pessimistic"})
        dispatch(order, "on_commit")
        mock_customer.ensure.assert_called_once()
        mock_stock.hold.assert_called_once()

    @patch("shopman.flows.notification")
    @patch("shopman.flows.payment")
    def test_confirmed_status_triggers_on_confirmed(self, mock_payment, mock_notification):
        order = _make_order(channel_config={"flow": "base"})
        dispatch(order, "on_confirmed")
        mock_payment.initiate.assert_called_once()

    @patch("shopman.flows.notification")
    @patch("shopman.flows.payment")
    @patch("shopman.flows.stock")
    @patch("shopman.flows.kds")
    def test_cancelled_status_triggers_on_cancelled(self, mock_kds, mock_stock, mock_payment, mock_notification):
        order = _make_order(channel_config={"flow": "base"})
        dispatch(order, "on_cancelled")
        mock_kds.cancel_tickets.assert_called_once()
        mock_stock.release.assert_called_once()

    @patch("shopman.flows.fiscal")
    @patch("shopman.flows.loyalty")
    def test_completed_status_triggers_on_completed(self, mock_loyalty, mock_fiscal):
        order = _make_order(channel_config={"flow": "base"})
        dispatch(order, "on_completed")
        mock_loyalty.earn.assert_called_once()
        mock_fiscal.emit.assert_called_once()


# ── Flow-specific dispatch ──


class TestFlowSpecificDispatch:
    @patch("shopman.flows.notification")
    @patch("shopman.flows.payment")
    def test_web_flow_dispatch(self, mock_payment, mock_notification):
        order = _make_order(channel_config={"flow": "web"})
        dispatch(order, "on_confirmed")
        # WebFlow inherits RemoteFlow → BaseFlow, so payment.initiate is called
        mock_payment.initiate.assert_called_once()

    @patch("shopman.flows.notification")
    def test_local_flow_on_confirmed_no_payment(self, mock_notification):
        order = _make_order(channel_config={"flow": "local"})
        dispatch(order, "on_confirmed")
        mock_notification.send.assert_called_once_with(order, "order_confirmed")

    @patch("shopman.flows.notification")
    def test_pos_flow_inherits_local(self, mock_notification):
        order = _make_order(channel_config={"flow": "pos"})
        dispatch(order, "on_confirmed")
        mock_notification.send.assert_called_once_with(order, "order_confirmed")

    @patch("shopman.flows.notification")
    @patch("shopman.flows.stock")
    def test_ifood_flow_inherits_marketplace(self, mock_stock, mock_notification):
        order = _make_order(
            channel_config={"flow": "ifood"},
            status="confirmed",
        )
        dispatch(order, "on_paid")
        mock_stock.fulfill.assert_called_once()


# ── Notification phases ──


class TestNotificationPhases:
    @patch("shopman.flows.notification")
    def test_on_dispatched_sends_notification(self, mock_notification):
        order = _make_order()
        BaseFlow().on_dispatched(order)
        mock_notification.send.assert_called_once_with(order, "order_dispatched")

    @patch("shopman.flows.notification")
    def test_on_delivered_sends_notification(self, mock_notification):
        order = _make_order()
        BaseFlow().on_delivered(order)
        mock_notification.send.assert_called_once_with(order, "order_delivered")
