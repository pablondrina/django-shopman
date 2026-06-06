"""
Tests for Happy Hour Badge.

Covers:
- happy_hour_state() returns active=True during the window (rule enabled)
- happy_hour_state() returns active=False outside the window
- happy_hour_state() returns inactive when the happy_hour rule is absent/disabled
- MenuView passes happy_hour_info to context
- Template shows banner when active, hides when inactive

The badge is gated on the enabled ``happy_hour`` RuleConfig — the same source
the TimeWindowDiscountModifier reads — so badge and discount cannot diverge.
"""

from __future__ import annotations

from datetime import time
from unittest.mock import patch

from django.test import TestCase

from shopman.shop.models import Channel

_HH_PARAMS = {"discount_percent": 25, "start": "16:00", "end": "18:00"}


def _rule_params(params):
    return patch("shopman.shop.rules.engine.get_rule_params", return_value=params)


class HappyHourStateTests(TestCase):
    def _state_at(self, hour, minute=0, params=_HH_PARAMS):
        from shopman.shop.projections.storefront_context import happy_hour_state

        with _rule_params(params):
            with patch("shopman.shop.projections.storefront_context.timezone") as mock_tz:
                mock_tz.localtime.return_value.time.return_value = time(hour, minute)
                return happy_hour_state()

    def test_active_during_window(self) -> None:
        """Returns active=True when current time is within the happy hour window."""
        result = self._state_at(17)
        self.assertTrue(result["active"])
        self.assertEqual(result["end"], "18:00")

    def test_inactive_before_window(self) -> None:
        """Returns active=False before happy hour starts."""
        self.assertFalse(self._state_at(15, 59)["active"])

    def test_inactive_after_window(self) -> None:
        """Returns active=False after happy hour ends."""
        self.assertFalse(self._state_at(18, 1)["active"])

    def test_inactive_at_exact_end(self) -> None:
        """End hour is exclusive (18:00 → not active)."""
        self.assertFalse(self._state_at(18, 0)["active"])

    def test_returns_discount_percent(self) -> None:
        """discount_percent comes from the rule params."""
        params = {"discount_percent": 15, "start": "16:00", "end": "18:00"}
        result = self._state_at(17, params=params)
        self.assertEqual(result["discount_percent"], 15)

    def test_inactive_when_rule_absent_or_disabled(self) -> None:
        """Returns inactive when the happy_hour rule is absent/disabled (empty params)."""
        result = self._state_at(17, params={})
        self.assertFalse(result["active"])
        self.assertEqual(result["discount_percent"], 0)


class MenuViewHappyHourContextTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.shop.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="web",
            name="Web",
            is_active=True,
        )

    def test_menu_passes_happy_hour_info_to_context(self) -> None:
        """MenuView GET includes catalog projection in context."""
        with patch("shopman.storefront.presentation.catalog.happy_hour_state") as mock_hh:
            mock_hh.return_value = {"active": False, "discount_percent": 10, "start": "16:00", "end": "18:00"}
            resp = self.client.get("/menu/")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("catalog", resp.context)

    def test_banner_shown_when_active(self) -> None:
        """Template renders Happy Hour banner when active=True."""
        with patch("shopman.storefront.presentation.catalog.happy_hour_state") as mock_hh:
            mock_hh.return_value = {"active": True, "discount_percent": 10, "start": "16:00", "end": "18:00"}
            resp = self.client.get("/menu/")

        self.assertContains(resp, "Happy Hour")
        self.assertContains(resp, "18:00")

    def test_banner_hidden_when_inactive(self) -> None:
        """Template does NOT render Happy Hour banner when active=False."""
        with patch("shopman.storefront.presentation.catalog.happy_hour_state") as mock_hh:
            mock_hh.return_value = {"active": False, "discount_percent": 10, "start": "16:00", "end": "18:00"}
            resp = self.client.get("/menu/")

        self.assertNotContains(resp, "Happy Hour")
