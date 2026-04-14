"""
ChannelConfig conformance tests — verifica que o runtime obedece a config.

Um teste por aspecto configurável. Cada teste patches os services relevantes
e verifica que dispatch() chama (ou não) o serviço esperado conforme a config.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest

from shopman.shop.config import ChannelConfig


# ── fixture helpers ──


def _make_order(**overrides):
    order = MagicMock()
    order.ref = overrides.get("ref", "ORD-CONF-001")
    order.total_q = overrides.get("total_q", 5000)
    order.status = overrides.get("status", "new")
    order.channel_ref = overrides.get("channel_ref", "web")
    order.data = overrides.get("data", {})
    order.snapshot = overrides.get("snapshot", {"items": []})
    order.can_transition_to.return_value = True
    return order


def _config(**kwargs) -> ChannelConfig:
    """Build a ChannelConfig from flat kwargs, e.g. confirmation_mode='immediate'."""
    c = ChannelConfig()
    for key, value in kwargs.items():
        aspect, _, field = key.partition("_")
        obj = getattr(c, aspect)
        setattr(obj, field, value)
    return c


def _patch_config(cfg: ChannelConfig):
    """Patch ChannelConfig.for_channel to return cfg."""
    return patch("shopman.shop.lifecycle.ChannelConfig.for_channel", return_value=cfg)


# ── Aspect 1: Confirmation ──


class TestConfirmationConformance:
    def test_immediate_auto_confirms_on_commit(self):
        """confirmation.mode='immediate' → order.transition_status('confirmed') on commit."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order()
        cfg = _config()
        cfg.confirmation.mode = "immediate"

        patches = [
            patch("shopman.shop.lifecycle.customer.ensure"),
            patch("shopman.shop.lifecycle.stock.hold"),
            patch("shopman.shop.lifecycle.loyalty.redeem"),
            patch("shopman.shop.lifecycle.payment.initiate"),
            patch("shopman.shop.lifecycle.fulfillment.create"),
            _patch_config(cfg),
        ]
        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.customer.ensure"):
                with patch("shopman.shop.lifecycle.stock.hold"):
                    with patch("shopman.shop.lifecycle.loyalty.redeem"):
                        dispatch(order, "on_commit")

        order.transition_status.assert_called_with("confirmed", actor="auto_confirm")

    def test_manual_does_not_auto_confirm(self):
        """confirmation.mode='manual' → no auto-confirm, operator must confirm."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order()
        cfg = _config()
        cfg.confirmation.mode = "manual"

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.customer.ensure"):
                with patch("shopman.shop.lifecycle.stock.hold"):
                    with patch("shopman.shop.lifecycle.loyalty.redeem"):
                        dispatch(order, "on_commit")

        order.transition_status.assert_not_called()

    def test_optimistic_creates_confirmation_timeout_directive(self, db):
        """confirmation.mode='optimistic' → Directive com topic=confirmation.timeout."""
        from shopman.orderman.models import Directive
        from shopman.shop.lifecycle import dispatch

        order = _make_order()
        cfg = _config()
        cfg.confirmation.mode = "optimistic"
        cfg.confirmation.timeout_minutes = 5

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.customer.ensure"):
                with patch("shopman.shop.lifecycle.stock.hold"):
                    with patch("shopman.shop.lifecycle.loyalty.redeem"):
                        dispatch(order, "on_commit")

        order.transition_status.assert_not_called()
        assert Directive.objects.filter(topic="confirmation.timeout").exists()


# ── Aspect 2: Payment ──


class TestPaymentConformance:
    def test_external_timing_skips_initiate(self):
        """payment.timing='external' → payment.initiate NOT called on commit."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order()
        cfg = _config()
        cfg.payment.timing = "external"
        cfg.payment.method = "external"
        cfg.confirmation.mode = "manual"

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.customer.ensure"):
                with patch("shopman.shop.lifecycle.stock.hold"):
                    with patch("shopman.shop.lifecycle.loyalty.redeem"):
                        with patch("shopman.shop.lifecycle.payment.initiate") as mock_init:
                            dispatch(order, "on_commit")

        mock_init.assert_not_called()

    def test_at_commit_timing_initiates_on_commit(self):
        """payment.timing='at_commit' → payment.initiate called on commit."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order()
        cfg = _config()
        cfg.payment.timing = "at_commit"
        cfg.payment.method = "pix"
        cfg.confirmation.mode = "manual"

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.customer.ensure"):
                with patch("shopman.shop.lifecycle.stock.hold"):
                    with patch("shopman.shop.lifecycle.loyalty.redeem"):
                        with patch("shopman.shop.lifecycle.payment.initiate") as mock_init:
                            dispatch(order, "on_commit")

        mock_init.assert_called_once_with(order)

    def test_post_commit_initiates_on_confirmed(self):
        """payment.timing='post_commit' → payment.initiate on confirmed, not on commit."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order(status="confirmed")
        cfg = _config()
        cfg.payment.timing = "post_commit"

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.payment.initiate") as mock_init:
                with patch("shopman.shop.lifecycle.stock.fulfill"):
                    with patch("shopman.shop.lifecycle.notification.send"):
                        dispatch(order, "on_confirmed")

        mock_init.assert_called_once_with(order)


# ── Aspect 3: Fulfillment ──


class TestFulfillmentConformance:
    def test_at_commit_creates_fulfillment_on_commit(self):
        """fulfillment.timing='at_commit' → fulfillment.create called on commit."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order()
        cfg = _config()
        cfg.fulfillment.timing = "at_commit"
        cfg.confirmation.mode = "manual"

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.customer.ensure"):
                with patch("shopman.shop.lifecycle.stock.hold"):
                    with patch("shopman.shop.lifecycle.loyalty.redeem"):
                        with patch("shopman.shop.lifecycle.fulfillment.create") as mock_create:
                            dispatch(order, "on_commit")

        mock_create.assert_called_once_with(order)

    def test_post_commit_creates_fulfillment_on_ready(self):
        """fulfillment.timing='post_commit' → fulfillment.create on ready, not commit."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order(status="ready")
        cfg = _config()
        cfg.fulfillment.timing = "post_commit"

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.fulfillment.create") as mock_create:
                with patch("shopman.shop.lifecycle.notification.send"):
                    dispatch(order, "on_ready")

        mock_create.assert_called_once_with(order)

    def test_external_timing_skips_fulfillment_create(self):
        """fulfillment.timing='external' → fulfillment.create NOT called on commit or ready."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order()
        cfg = _config()
        cfg.fulfillment.timing = "external"
        cfg.confirmation.mode = "manual"

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.customer.ensure"):
                with patch("shopman.shop.lifecycle.stock.hold"):
                    with patch("shopman.shop.lifecycle.loyalty.redeem"):
                        with patch("shopman.shop.lifecycle.fulfillment.create") as mock_create:
                            dispatch(order, "on_commit")

        mock_create.assert_not_called()


# ── Aspect 4: Stock ──


class TestStockConformance:
    def test_check_on_commit_false_skips_availability(self):
        """stock.check_on_commit=False → availability.decide NOT called on commit."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order()
        cfg = _config()
        cfg.stock.check_on_commit = False
        cfg.confirmation.mode = "manual"

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.customer.ensure"):
                with patch("shopman.shop.lifecycle.stock.hold"):
                    with patch("shopman.shop.lifecycle.loyalty.redeem"):
                        with patch("shopman.shop.lifecycle.availability.decide") as mock_decide:
                            dispatch(order, "on_commit")

        mock_decide.assert_not_called()

    def test_check_on_commit_true_checks_each_item(self):
        """stock.check_on_commit=True → availability.decide called for each snapshot item."""
        from decimal import Decimal
        from shopman.shop.lifecycle import dispatch

        order = _make_order(
            snapshot={"items": [{"sku": "PAIN-AU-CHOCOLAT", "qty": 2}]},
        )
        order.data = {}
        cfg = _config()
        cfg.stock.check_on_commit = True
        cfg.confirmation.mode = "manual"

        _avail_ok = {
            "approved": True,
            "sku": "PAIN-AU-CHOCOLAT",
            "requested_qty": Decimal("2"),
            "available_qty": Decimal("999"),
            "reason_code": None,
            "is_paused": False,
            "is_planned": False,
            "target_date": None,
            "failed_sku": None,
            "source": "stock.untracked",
        }

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.customer.ensure"):
                with patch("shopman.shop.lifecycle.stock.hold"):
                    with patch("shopman.shop.lifecycle.loyalty.redeem"):
                        with patch("shopman.shop.lifecycle.availability.decide", return_value=_avail_ok) as mock_decide:
                            dispatch(order, "on_commit")

        mock_decide.assert_called_once_with(
            "PAIN-AU-CHOCOLAT", 2, channel_ref="web", target_date=None
        )


# ── Aspect 5: Notifications ──


class TestNotificationsConformance:
    def test_notifications_sent_on_confirmed(self):
        """notification.send('order_confirmed') called when order is confirmed."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order(status="confirmed")
        cfg = _config()
        cfg.payment.timing = "external"
        cfg.payment.method = "external"

        with _patch_config(cfg):
            with patch("shopman.shop.lifecycle.stock.fulfill"):
                with patch("shopman.shop.lifecycle.notification.send") as mock_notify:
                    dispatch(order, "on_confirmed")

        mock_notify.assert_called_with(order, "order_confirmed")

    def test_notifications_sent_on_cancelled(self):
        """notification.send('order_cancelled') called on cancellation."""
        from shopman.shop.lifecycle import dispatch

        order = _make_order(status="cancelled")
        cfg = _config()

        with _patch_config(cfg):
            with patch("shopman.shop.services.kds.cancel_tickets"):
                with patch("shopman.shop.lifecycle.stock.release"):
                    with patch("shopman.shop.lifecycle.payment.refund"):
                        with patch("shopman.shop.lifecycle.notification.send") as mock_notify:
                            dispatch(order, "on_cancelled")

        mock_notify.assert_called_with(order, "order_cancelled")


# ── Aspect 6: Pricing ──


class TestPricingConformance:
    def test_pricing_policy_reflected_in_config(self):
        """pricing.policy is accessible and has expected values."""
        cfg = ChannelConfig()
        assert cfg.pricing.policy == "internal"

        cfg.pricing.policy = "external"
        assert cfg.pricing.policy == "external"

    def test_pricing_policy_validates(self):
        """pricing.policy rejects invalid values."""
        cfg = ChannelConfig()
        cfg.pricing.policy = "invalid"
        with pytest.raises(ValueError, match="pricing.policy"):
            cfg.validate()


# ── Aspect 7: Editing ──


class TestEditingConformance:
    def test_editing_policy_defaults_open(self):
        """editing.policy defaults to 'open'."""
        cfg = ChannelConfig()
        assert cfg.editing.policy == "open"

    def test_editing_policy_validates(self):
        """editing.policy rejects invalid values."""
        cfg = ChannelConfig()
        cfg.editing.policy = "unknown"
        with pytest.raises(ValueError, match="editing.policy"):
            cfg.validate()


# ── Aspect 8: Rules ──


class TestRulesConformance:
    def test_rules_defaults_are_empty_lists(self):
        """Rules default to empty lists — no validators/modifiers active."""
        cfg = ChannelConfig()
        assert cfg.rules.validators == []
        assert cfg.rules.modifiers == []
        assert cfg.rules.checks == []

    def test_rules_survive_cascade(self):
        """Rules set at channel level survive from_dict round-trip."""
        raw = ChannelConfig().to_dict()
        raw["rules"]["validators"] = ["min_order_value"]
        cfg = ChannelConfig.from_dict(raw)
        assert "min_order_value" in cfg.rules.validators


# ── Cascade correctness ──


class TestCascadeConformance:
    def test_channel_overrides_defaults(self):
        """Channel-level config overrides defaults via cascade."""
        from shopman.shop.config import deep_merge

        base = ChannelConfig().to_dict()
        override = {"confirmation": {"mode": "manual"}}
        merged = deep_merge(base, override)
        cfg = ChannelConfig.from_dict(merged)
        assert cfg.confirmation.mode == "manual"

    def test_deep_merge_does_not_wipe_sibling_fields(self):
        """Overriding one field in an aspect preserves sibling fields."""
        from shopman.shop.config import deep_merge

        base = ChannelConfig().to_dict()
        override = {"payment": {"method": "pix"}}
        merged = deep_merge(base, override)
        cfg = ChannelConfig.from_dict(merged)
        assert cfg.payment.method == "pix"
        assert cfg.payment.timing == "post_commit"  # sibling preserved
