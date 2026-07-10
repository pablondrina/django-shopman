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
        from shopman.storefront.presentation.shop_status import _shop_status

        shop = MagicMock()
        shop.opening_hours = None
        with patch("shopman.shop.models.Shop.load", return_value=shop):
            st = _shop_status()
            assert st["is_open"] is True
            assert st["label"] == "Aberto agora"

    def test_business_hours_rule_not_outside_without_shop_hours(self):
        from shopman.shop.rules.validation import BusinessHoursRule

        rule = BusinessHoursRule()
        with patch.object(rule, "_get_opening_hours", return_value=None):
            assert rule._check_outside_hours() is False

    def test_shop_status_label_owned_by_registry(self):
        """O badge (label) vem do registro omotenashi (SHOP_STATUS_*), granular:
        fechado antes de abrir → "Fechado. Abre às {hora}". A ``message`` (spine,
        banner global não renderizado na home) segue sua própria fonte."""
        from shopman.storefront.presentation.shop_status import _shop_status

        state = SimpleNamespace(
            is_open=False,
            is_closed=True,
            opens_at="09:00",
            closes_at="18:00",
            closure_source="",
            closed_reason="",
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
        assert st["label"] == "Fechado. Abre às 9h"

    def test_shop_status_label_open_until_closing_hour(self):
        """Aberto com horário de fechamento → "Aberto até {hora}" (registro)."""
        from shopman.storefront.presentation.shop_status import _shop_status

        state = SimpleNamespace(
            is_open=True,
            is_closed=False,
            opens_at="07:00",
            closes_at="19:00",
            closure_source="",
            closed_reason="",
            message="Aberto até 19h",
            next_open_at=None,
            resolved_at=datetime(2026, 5, 15, 10, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
        )

        with patch("shopman.shop.services.business_calendar.current_business_state", return_value=state):
            st = _shop_status()

        assert st["label"] == "Aberto até 19h"

    def test_opening_hours_format_uses_plain_preposition(self):
        from shopman.storefront.presentation.shop_status import _format_opening_hours

        shop = MagicMock()
        shop.opening_hours = {
            "monday": {"open": "09:00", "close": "18:00"},
            "tuesday": {"open": "09:00", "close": "18:00"},
        }

        with patch("shopman.shop.models.Shop.load", return_value=shop):
            hours = _format_opening_hours()

        assert {"label": "Segunda e Terça", "hours": "9h às 18h"} in hours
        assert all("—" not in entry["hours"] for entry in hours)
