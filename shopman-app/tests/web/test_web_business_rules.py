"""Tests for WP-P2: Storefront visibility of business rules + validator unit tests."""
from __future__ import annotations

from datetime import time, timedelta
from unittest.mock import Mock, patch

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.utils import timezone

from shop.models import Promotion, Shop
from shop.validators import BusinessHoursValidator, MinimumOrderValidator

pytestmark = pytest.mark.django_db


# ── Shop Status ──────────────────────────────────────────────────────────


class TestShopStatus:
    def _patch_localtime(self, dt):
        return patch("channels.web.views._helpers.timezone.localtime", return_value=dt)

    def test_shop_status_open(self, client: Client, shop_instance: Shop):
        shop_instance.opening_hours = {
            "monday": {"open": "06:00", "close": "20:00"},
            "tuesday": {"open": "06:00", "close": "20:00"},
            "wednesday": {"open": "06:00", "close": "20:00"},
            "thursday": {"open": "06:00", "close": "20:00"},
            "friday": {"open": "06:00", "close": "20:00"},
            "saturday": {"open": "07:00", "close": "13:00"},
        }
        shop_instance.save()

        # Mock to Wednesday 10:00
        mock_now = timezone.now().replace(hour=10, minute=0, second=0)
        # Force the weekday to Wednesday
        while mock_now.strftime("%A").lower() != "wednesday":
            mock_now += timedelta(days=1)

        with self._patch_localtime(mock_now):
            from channels.web.views._helpers import _shop_status

            status = _shop_status()
            assert status["is_open"] is True
            assert "Aberto" in status["message"]

    def test_shop_status_closed(self, client: Client, shop_instance: Shop):
        shop_instance.opening_hours = {
            "monday": {"open": "06:00", "close": "20:00"},
            "tuesday": {"open": "06:00", "close": "20:00"},
            "wednesday": {"open": "06:00", "close": "20:00"},
            "thursday": {"open": "06:00", "close": "20:00"},
            "friday": {"open": "06:00", "close": "20:00"},
            "saturday": {"open": "07:00", "close": "13:00"},
        }
        shop_instance.save()

        # Mock to Wednesday 22:00
        mock_now = timezone.now().replace(hour=22, minute=0, second=0)
        while mock_now.strftime("%A").lower() != "wednesday":
            mock_now += timedelta(days=1)

        with self._patch_localtime(mock_now):
            from channels.web.views._helpers import _shop_status

            status = _shop_status()
            assert status["is_open"] is False
            assert "Fechado" in status["message"]

    def test_shop_status_closed_today(self, client: Client, shop_instance: Shop):
        """Day not in opening_hours shows 'Fechado hoje'."""
        shop_instance.opening_hours = {
            "tuesday": {"open": "06:00", "close": "20:00"},
        }
        shop_instance.save()

        # Mock to Monday (not in hours)
        mock_now = timezone.now().replace(hour=10, minute=0, second=0)
        while mock_now.strftime("%A").lower() != "monday":
            mock_now += timedelta(days=1)

        with self._patch_localtime(mock_now):
            from channels.web.views._helpers import _shop_status

            status = _shop_status()
            assert status["is_open"] is False
            assert "Fechado hoje" in status["message"]

    def test_shop_status_banner_in_page(self, client: Client, shop_instance: Shop):
        """Shop status message appears in the menu page via context."""
        shop_instance.opening_hours = {
            "monday": {"open": "06:00", "close": "20:00"},
            "tuesday": {"open": "06:00", "close": "20:00"},
            "wednesday": {"open": "06:00", "close": "20:00"},
            "thursday": {"open": "06:00", "close": "20:00"},
            "friday": {"open": "06:00", "close": "20:00"},
            "saturday": {"open": "07:00", "close": "13:00"},
        }
        shop_instance.save()

        # Mock to Wednesday 10:00
        mock_now = timezone.now().replace(hour=10, minute=0, second=0)
        while mock_now.strftime("%A").lower() != "wednesday":
            mock_now += timedelta(days=1)

        with patch("channels.web.views._helpers.timezone.localtime", return_value=mock_now):
            resp = client.get("/menu/")
            assert resp.status_code == 200
            # shop_status should be in context
            shop_status = resp.context.get("shop_status")
            assert shop_status is not None
            assert shop_status["is_open"] is True
            assert "Aberto" in shop_status["message"]


# ── Minimum Order Warning ────────────────────────────────────────────────


class TestCartMinimumOrderWarning:
    def test_cart_page_redirects_to_menu(self, client: Client):
        """Cart page redirects to menu (drawer is the cart now)."""
        resp = client.get("/cart/")
        assert resp.status_code == 302
        assert "open_cart=1" in resp.url

    def test_cart_drawer_minimum_order_warning(self, client: Client, channel, product):
        """Cart drawer shows min order progress when below minimum."""
        channel.config = {"rules": {"validators": ["shop.minimum_order"], "minimum_order_q": 5000}}
        channel.save()

        client.post("/cart/add/", {"sku": product.sku, "qty": 1})
        resp = client.get("/cart/drawer/")
        assert resp.status_code == 200
        assert resp.context.get("min_order_progress") is not None

    def test_cart_drawer_no_warning_above_minimum(self, client: Client, channel, product):
        """No warning in drawer when cart is above minimum."""
        channel.config = {"rules": {"validators": ["shop.minimum_order"], "minimum_order_q": 50}}
        channel.save()

        client.post("/cart/add/", {"sku": product.sku, "qty": 1})
        resp = client.get("/cart/drawer/")
        assert resp.status_code == 200
        assert resp.context.get("min_order_progress") is None


# ── Promotions in Catalog ────────────────────────────────────────────────


class TestMenuPromotions:
    def test_menu_shows_active_promotions(self, client: Client, collection, collection_item, product):
        """Active promotions appear in menu context."""
        now = timezone.now()
        Promotion.objects.create(
            name="Semana do Pão",
            type="percent",
            value=15,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=7),
            is_active=True,
        )
        resp = client.get("/menu/")
        assert resp.status_code == 200
        promotions = resp.context.get("promotions", [])
        assert len(promotions) == 1
        assert promotions[0]["name"] == "Semana do Pão"
        assert "15% OFF" in promotions[0]["discount_label"]

    def test_menu_hides_expired_promotions(self, client: Client, collection, collection_item, product):
        """Expired promotions do not appear."""
        now = timezone.now()
        Promotion.objects.create(
            name="Promoção Expirada",
            type="percent",
            value=10,
            valid_from=now - timedelta(days=30),
            valid_until=now - timedelta(days=1),
            is_active=True,
        )
        resp = client.get("/menu/")
        assert resp.status_code == 200
        promotions = resp.context.get("promotions", [])
        assert len(promotions) == 0

    def test_menu_hides_inactive_promotions(self, client: Client, collection, collection_item, product):
        """Inactive promotions do not appear even if within date range."""
        now = timezone.now()
        Promotion.objects.create(
            name="Promoção Desativada",
            type="percent",
            value=10,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=7),
            is_active=False,
        )
        resp = client.get("/menu/")
        assert resp.status_code == 200
        promotions = resp.context.get("promotions", [])
        assert len(promotions) == 0


# ── Promotion Badge on Product Card ──────────────────────────────────────


class TestProductPromoBadge:
    def test_product_card_shows_promo_badge(self, client: Client, collection, collection_item, product):
        """Product covered by active promotion has promo_badge in annotated data."""
        now = timezone.now()
        Promotion.objects.create(
            name="Semana do Pão",
            type="percent",
            value=15,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=7),
            collections=["paes"],
            is_active=True,
        )
        resp = client.get("/menu/")
        assert resp.status_code == 200
        # Find the product in sections
        for section in resp.context["sections"]:
            for item in section["products"]:
                if item["product"].sku == product.sku:
                    assert item["promo_badge"] is not None
                    assert "-15%" in item["promo_badge"]["label"]
                    return
        pytest.fail("Product not found in sections")

    def test_product_card_no_badge_without_promo(self, client: Client, collection, collection_item, product):
        """Product without matching promotion has no promo_badge."""
        resp = client.get("/menu/")
        assert resp.status_code == 200
        for section in resp.context["sections"]:
            for item in section["products"]:
                if item["product"].sku == product.sku:
                    assert item["promo_badge"] is None
                    return
        pytest.fail("Product not found in sections")


# ── BusinessHoursValidator — Unit Tests ──────────────────────────────────


class TestBusinessHoursValidator:
    """Tests for BusinessHoursValidator with Shop.opening_hours integration."""

    def _mock_localtime(self, hour, weekday="wednesday"):
        """Create a mock datetime at given hour on given weekday."""
        from datetime import timedelta

        mock_now = timezone.now().replace(hour=hour, minute=0, second=0)
        while mock_now.strftime("%A").lower() != weekday:
            mock_now += timedelta(days=1)
        return mock_now

    def test_rejects_outside_hours_fallback(self):
        """Without Shop, falls back to constructor defaults."""
        validator = BusinessHoursValidator(start=time(6, 0), end=time(20, 0))
        mock_now = self._mock_localtime(22)
        with patch("shop.validators.timezone.localtime", return_value=mock_now), \
             patch.object(BusinessHoursValidator, "_get_opening_hours", return_value=None):
            with pytest.raises(ValidationError, match="Pedidos aceitos apenas entre"):
                validator.validate(channel=Mock(), session=Mock(), ctx={})

    def test_allows_within_hours_fallback(self):
        """Without Shop, allows within constructor defaults."""
        validator = BusinessHoursValidator(start=time(6, 0), end=time(20, 0))
        mock_now = self._mock_localtime(10)
        with patch("shop.validators.timezone.localtime", return_value=mock_now), \
             patch.object(BusinessHoursValidator, "_get_opening_hours", return_value=None):
            validator.validate(channel=Mock(), session=Mock(), ctx={})

    def test_uses_shop_opening_hours(self):
        """With Shop.opening_hours, uses actual hours for the day."""
        validator = BusinessHoursValidator()
        opening_hours = {
            "wednesday": {"open": "09:00", "close": "18:00"},
        }
        # 08:30 on Wednesday — before shop opens
        mock_now = self._mock_localtime(8, "wednesday").replace(minute=30)
        with patch("shop.validators.timezone.localtime", return_value=mock_now), \
             patch.object(BusinessHoursValidator, "_get_opening_hours", return_value=opening_hours):
            with pytest.raises(ValidationError, match="09:00.*18:00"):
                validator.validate(channel=Mock(), session=Mock(), ctx={})

    def test_rejects_closed_day(self):
        """Day not in opening_hours raises 'closed today' error."""
        validator = BusinessHoursValidator()
        opening_hours = {
            "monday": {"open": "09:00", "close": "18:00"},
            # sunday not present = closed
        }
        mock_now = self._mock_localtime(10, "sunday")
        with patch("shop.validators.timezone.localtime", return_value=mock_now), \
             patch.object(BusinessHoursValidator, "_get_opening_hours", return_value=opening_hours):
            with pytest.raises(ValidationError, match="domingo"):
                validator.validate(channel=Mock(), session=Mock(), ctx={})

    def test_allows_within_shop_hours(self):
        """Within shop hours on a valid day passes."""
        validator = BusinessHoursValidator()
        opening_hours = {
            "wednesday": {"open": "09:00", "close": "18:00"},
        }
        mock_now = self._mock_localtime(12, "wednesday")
        with patch("shop.validators.timezone.localtime", return_value=mock_now), \
             patch.object(BusinessHoursValidator, "_get_opening_hours", return_value=opening_hours):
            validator.validate(channel=Mock(), session=Mock(), ctx={})

    def test_rejects_at_closing_time(self):
        """Exactly at closing time (boundary) should reject."""
        validator = BusinessHoursValidator()
        opening_hours = {"wednesday": {"open": "09:00", "close": "18:00"}}
        mock_now = self._mock_localtime(18, "wednesday")
        with patch("shop.validators.timezone.localtime", return_value=mock_now), \
             patch.object(BusinessHoursValidator, "_get_opening_hours", return_value=opening_hours):
            with pytest.raises(ValidationError):
                validator.validate(channel=Mock(), session=Mock(), ctx={})

    def test_allows_at_opening_time(self):
        """Exactly at opening time (boundary) should allow."""
        validator = BusinessHoursValidator()
        opening_hours = {"wednesday": {"open": "09:00", "close": "18:00"}}
        mock_now = self._mock_localtime(9, "wednesday")
        with patch("shop.validators.timezone.localtime", return_value=mock_now), \
             patch.object(BusinessHoursValidator, "_get_opening_hours", return_value=opening_hours):
            validator.validate(channel=Mock(), session=Mock(), ctx={})

    def test_custom_hours_fallback(self):
        """Custom start/end hours work when Shop unavailable."""
        validator = BusinessHoursValidator(start=time(8, 0), end=time(18, 0))
        mock_now = self._mock_localtime(7)
        with patch("shop.validators.timezone.localtime", return_value=mock_now), \
             patch.object(BusinessHoursValidator, "_get_opening_hours", return_value=None):
            with pytest.raises(ValidationError):
                validator.validate(channel=Mock(), session=Mock(), ctx={})

    def test_code_and_stage(self):
        v = BusinessHoursValidator()
        assert v.code == "shop.business_hours"
        assert v.stage == "commit"


# ── MinimumOrderValidator — Unit Tests ───────────────────────────────────


class TestMinimumOrderValidator:
    def _mock_channel(self, ref="whatsapp"):
        ch = Mock()
        ch.ref = ref
        return ch

    def _mock_session(self, items, fulfillment_type="delivery"):
        s = Mock()
        s.items = items
        s.data = {"fulfillment_type": fulfillment_type} if fulfillment_type else {}
        return s

    def test_rejects_below_threshold(self):
        """Orders below minimum raise ValidationError."""
        validator = MinimumOrderValidator(minimum_q=1000)
        session = self._mock_session([{"line_total_q": 500}])
        with pytest.raises(ValidationError, match="Pedido minimo para delivery"):
            validator.validate(channel=self._mock_channel(), session=session, ctx={})

    def test_allows_above_threshold(self):
        """Orders above minimum pass validation."""
        validator = MinimumOrderValidator(minimum_q=1000)
        session = self._mock_session([{"line_total_q": 1500}])
        validator.validate(channel=self._mock_channel(), session=session, ctx={})  # no exception

    def test_allows_exactly_at_threshold(self):
        """Orders exactly at minimum pass validation."""
        validator = MinimumOrderValidator(minimum_q=1000)
        session = self._mock_session([{"line_total_q": 1000}])
        validator.validate(channel=self._mock_channel(), session=session, ctx={})  # no exception

    def test_skips_pickup_fulfillment(self):
        """Pickup orders skip validation entirely regardless of channel."""
        validator = MinimumOrderValidator(minimum_q=1000)
        session = self._mock_session([{"line_total_q": 100}], fulfillment_type="pickup")
        # Should NOT raise — fulfillment_type is pickup
        validator.validate(channel=self._mock_channel(), session=session, ctx={})

    def test_applies_to_delivery_on_any_channel(self):
        """Delivery fulfillment_type triggers validation on any channel (whatsapp, web, etc.)."""
        validator = MinimumOrderValidator(minimum_q=1000)
        session = self._mock_session([{"line_total_q": 500}], fulfillment_type="delivery")
        with pytest.raises(ValidationError):
            validator.validate(channel=self._mock_channel(ref="whatsapp"), session=session, ctx={})

    def test_fallback_to_channel_ref(self):
        """When session has no fulfillment_type, falls back to channel ref containing 'delivery'."""
        validator = MinimumOrderValidator(minimum_q=1000)
        session = self._mock_session([{"line_total_q": 500}], fulfillment_type="")
        with pytest.raises(ValidationError):
            validator.validate(channel=self._mock_channel(ref="delivery"), session=session, ctx={})

    def test_no_fulfillment_type_non_delivery_channel_skips(self):
        """No fulfillment_type + non-delivery channel ref → skip validation."""
        validator = MinimumOrderValidator(minimum_q=1000)
        session = self._mock_session([{"line_total_q": 100}], fulfillment_type="")
        validator.validate(channel=self._mock_channel(ref="pos"), session=session, ctx={})

    def test_sums_multiple_items(self):
        """Total is sum of all items' line_total_q."""
        validator = MinimumOrderValidator(minimum_q=1000)
        session = self._mock_session([
            {"line_total_q": 400},
            {"line_total_q": 300},
            {"line_total_q": 400},
        ])
        # Total = 1100, above 1000
        validator.validate(channel=self._mock_channel(), session=session, ctx={})  # no exception

    def test_error_message_format(self):
        """Error message contains formatted minimum value."""
        validator = MinimumOrderValidator(minimum_q=2500)
        session = self._mock_session([{"line_total_q": 100}])
        with pytest.raises(ValidationError, match="R\\$ 25,00"):
            validator.validate(channel=self._mock_channel(), session=session, ctx={})

    def test_code_and_stage(self):
        v = MinimumOrderValidator()
        assert v.code == "shop.minimum_order"
        assert v.stage == "commit"
