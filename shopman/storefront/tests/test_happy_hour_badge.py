"""
Tests for Happy Hour Badge.

Covers:
- happy_hour_state() returns active=True during happy hour window
- happy_hour_state() returns active=False outside window
- happy_hour_state() returns inactive when no modifier registered
- MenuView passes happy_hour_info to context
- Template shows banner when active, hides when inactive
"""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from shopman.shop.models import Channel


def _fake_modifiers_with_happy_hour():
    """Return a modifier list that includes a happy hour modifier."""
    return [SimpleNamespace(code="shop.happy_hour", order=65)]


def _fake_modifiers_empty():
    return []


class HappyHourStateTests(TestCase):
    def test_active_during_window(self) -> None:
        """Returns active=True when current time is within the happy hour window."""
        from shopman.shop.services.storefront_context import happy_hour_state

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.orderman.registry.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.shop.services.storefront_context.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(17, 0)
                    result = happy_hour_state()

        self.assertTrue(result["active"])
        self.assertEqual(result["end"], "18:00")

    def test_inactive_before_window(self) -> None:
        """Returns active=False before happy hour starts."""
        from shopman.shop.services.storefront_context import happy_hour_state

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.orderman.registry.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.shop.services.storefront_context.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(15, 59)
                    result = happy_hour_state()

        self.assertFalse(result["active"])

    def test_inactive_after_window(self) -> None:
        """Returns active=False after happy hour ends."""
        from shopman.shop.services.storefront_context import happy_hour_state

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.orderman.registry.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.shop.services.storefront_context.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(18, 0)
                    result = happy_hour_state()

        self.assertFalse(result["active"])

    def test_inactive_at_exact_end(self) -> None:
        """End hour is exclusive (18:00 → not active)."""
        from shopman.shop.services.storefront_context import happy_hour_state

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.orderman.registry.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.shop.services.storefront_context.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(18, 0)
                    result = happy_hour_state()

        self.assertFalse(result["active"])

    def test_returns_discount_percent(self) -> None:
        """discount_percent comes from settings."""
        from shopman.shop.services.storefront_context import happy_hour_state

        with override_settings(
            SHOPMAN_HAPPY_HOUR_START="16:00",
            SHOPMAN_HAPPY_HOUR_END="18:00",
            SHOPMAN_HAPPY_HOUR_DISCOUNT_PERCENT=15,
        ):
            with patch("shopman.orderman.registry.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.shop.services.storefront_context.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(17, 0)
                    result = happy_hour_state()

        self.assertEqual(result["discount_percent"], 15)

    def test_inactive_when_no_modifier_registered(self) -> None:
        """Returns inactive when no happy hour modifier is in the registry."""
        from shopman.shop.services.storefront_context import happy_hour_state

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.orderman.registry.get_modifiers", _fake_modifiers_empty):
                with patch("shopman.shop.services.storefront_context.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(17, 0)
                    result = happy_hour_state()

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
        with patch("shopman.storefront.projections.catalog.happy_hour_state") as mock_hh:
            mock_hh.return_value = {"active": False, "discount_percent": 10, "start": "16:00", "end": "18:00"}
            resp = self.client.get("/menu/")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("catalog", resp.context)

    def test_banner_shown_when_active(self) -> None:
        """Template renders Happy Hour banner when active=True."""
        with patch("shopman.storefront.projections.catalog.happy_hour_state") as mock_hh:
            mock_hh.return_value = {"active": True, "discount_percent": 10, "start": "16:00", "end": "18:00"}
            resp = self.client.get("/menu/")

        self.assertContains(resp, "Happy Hour")
        self.assertContains(resp, "18:00")

    def test_banner_hidden_when_inactive(self) -> None:
        """Template does NOT render Happy Hour banner when active=False."""
        with patch("shopman.storefront.projections.catalog.happy_hour_state") as mock_hh:
            mock_hh.return_value = {"active": False, "discount_percent": 10, "start": "16:00", "end": "18:00"}
            resp = self.client.get("/menu/")

        self.assertNotContains(resp, "Happy Hour")
