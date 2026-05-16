"""Tests for shop status helpers (storefront display layer)."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

pytestmark = pytest.mark.django_db


class TestShopStatusVsBusinessHoursRule:
    """Sem horários no Shop, vitrine e validador não devem divergir (sempre "aberto")."""

    def test_shop_status_open_without_hours(self):
        from shopman.storefront.projections.shop_status import _shop_status

        shop = MagicMock()
        shop.opening_hours = None
        with patch("shopman.shop.models.Shop.load", return_value=shop):
            st = _shop_status()
            assert st["is_open"] is True

    def test_business_hours_rule_not_outside_without_shop_hours(self):
        from shopman.shop.rules.validation import BusinessHoursRule

        rule = BusinessHoursRule()
        with patch.object(rule, "_get_opening_hours", return_value=None):
            assert rule._check_outside_hours() is False

    def test_shop_status_does_not_duplicate_next_opening_copy(self):
        from shopman.storefront.projections.shop_status import _shop_status

        state = SimpleNamespace(
            is_open=False,
            is_closed=True,
            opens_at="09:00",
            closes_at="18:00",
            message="Fechado. Abrimos às 9h",
            next_open_at=datetime(2026, 5, 15, 9, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
            resolved_at=datetime(2026, 5, 15, 8, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        )

        with (
            patch("shopman.shop.services.business_calendar.current_business_state", return_value=state),
            patch("shopman.shop.services.business_calendar.format_next_opening", return_value="hoje às 9h"),
        ):
            st = _shop_status()

        assert st["message"] == "Fechado. Abrimos às 9h"

    def test_opening_hours_format_uses_plain_preposition(self):
        from shopman.storefront.projections.shop_status import _format_opening_hours

        shop = MagicMock()
        shop.opening_hours = {
            "monday": {"open": "09:00", "close": "18:00"},
            "tuesday": {"open": "09:00", "close": "18:00"},
        }

        with patch("shopman.shop.models.Shop.load", return_value=shop):
            hours = _format_opening_hours()

        assert {"label": "Segunda e Terça", "hours": "9h às 18h"} in hours
        assert all("—" not in entry["hours"] for entry in hours)
