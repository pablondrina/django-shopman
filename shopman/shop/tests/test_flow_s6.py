"""WP-S6 — Flow Review: alinhamento storefront vs regras e fumaça de cancelamento."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

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
