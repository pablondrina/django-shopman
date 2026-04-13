"""
Tests for WP-R8 — Happy Hour Badge.

Covers:
- _is_happy_hour_active() returns active=True during happy hour window
- _is_happy_hour_active() returns active=False outside window
- _is_happy_hour_active() returns inactive when no modifier registered
- MenuView passes happy_hour_info to context
- Template shows banner when active, hides when inactive
"""

from __future__ import annotations

from datetime import time
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings

from shopman.models import Channel


def _fake_modifiers_with_happy_hour():
    """Return a modifier list that includes a happy hour modifier."""
    return [SimpleNamespace(code="shop.happy_hour", order=65)]


def _fake_modifiers_empty():
    return []


class IsHappyHourActiveTests(TestCase):
    def test_active_during_window(self) -> None:
        """Returns active=True when current time is within the happy hour window."""
        from shopman.web.views._helpers import _is_happy_hour_active

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.web.views._helpers.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.web.views._helpers.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(17, 0)
                    result = _is_happy_hour_active()

        self.assertTrue(result["active"])
        self.assertEqual(result["end"], "18:00")

    def test_inactive_before_window(self) -> None:
        """Returns active=False before happy hour starts."""
        from shopman.web.views._helpers import _is_happy_hour_active

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.web.views._helpers.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.web.views._helpers.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(15, 59)
                    result = _is_happy_hour_active()

        self.assertFalse(result["active"])

    def test_inactive_after_window(self) -> None:
        """Returns active=False after happy hour ends."""
        from shopman.web.views._helpers import _is_happy_hour_active

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.web.views._helpers.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.web.views._helpers.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(18, 0)
                    result = _is_happy_hour_active()

        self.assertFalse(result["active"])

    def test_inactive_at_exact_end(self) -> None:
        """End hour is exclusive (18:00 → not active)."""
        from shopman.web.views._helpers import _is_happy_hour_active

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.web.views._helpers.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.web.views._helpers.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(18, 0)
                    result = _is_happy_hour_active()

        self.assertFalse(result["active"])

    def test_returns_discount_percent(self) -> None:
        """discount_percent comes from settings."""
        from shopman.web.views._helpers import _is_happy_hour_active

        with override_settings(
            SHOPMAN_HAPPY_HOUR_START="16:00",
            SHOPMAN_HAPPY_HOUR_END="18:00",
            SHOPMAN_HAPPY_HOUR_DISCOUNT_PERCENT=15,
        ):
            with patch("shopman.web.views._helpers.get_modifiers", _fake_modifiers_with_happy_hour):
                with patch("shopman.web.views._helpers.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(17, 0)
                    result = _is_happy_hour_active()

        self.assertEqual(result["discount_percent"], 15)

    def test_inactive_when_no_modifier_registered(self) -> None:
        """Returns inactive when no happy hour modifier is in the registry."""
        from shopman.web.views._helpers import _is_happy_hour_active

        with override_settings(SHOPMAN_HAPPY_HOUR_START="16:00", SHOPMAN_HAPPY_HOUR_END="18:00"):
            with patch("shopman.web.views._helpers.get_modifiers", _fake_modifiers_empty):
                with patch("shopman.web.views._helpers.timezone") as mock_tz:
                    mock_tz.localtime.return_value.time.return_value = time(17, 0)
                    result = _is_happy_hour_active()

        self.assertFalse(result["active"])
        self.assertEqual(result["discount_percent"], 0)


class MenuViewHappyHourContextTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        from shopman.models import Shop
        Shop.objects.create(name="Test Shop", brand_name="Test")
        Channel.objects.create(
            ref="web",
            name="Web",
            is_active=True,
        )

    def test_menu_passes_happy_hour_info_to_context(self) -> None:
        """MenuView GET passes happy_hour_info dict to template context."""
        with patch("shopman.web.views.catalog._is_happy_hour_active") as mock_hh:
            mock_hh.return_value = {"active": False, "discount_percent": 10, "start": "16:00", "end": "18:00"}
            resp = self.client.get("/menu/")

        self.assertEqual(resp.status_code, 200)
        self.assertIn("happy_hour_info", resp.context)

    def test_banner_shown_when_active(self) -> None:
        """Template renders Happy Hour banner when active=True."""
        with patch("shopman.web.views.catalog._is_happy_hour_active") as mock_hh:
            mock_hh.return_value = {"active": True, "discount_percent": 10, "start": "16:00", "end": "18:00"}
            resp = self.client.get("/menu/")

        self.assertContains(resp, "Happy Hour")
        self.assertContains(resp, "18:00")

    def test_banner_hidden_when_inactive(self) -> None:
        """Template does NOT render Happy Hour banner when active=False."""
        with patch("shopman.web.views.catalog._is_happy_hour_active") as mock_hh:
            mock_hh.return_value = {"active": False, "discount_percent": 10, "start": "16:00", "end": "18:00"}
            resp = self.client.get("/menu/")

        self.assertNotContains(resp, "Happy Hour")
