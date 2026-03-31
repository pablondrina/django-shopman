"""Tests for admin parity (WP-P5)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from shopman.ordering.models import Channel, Fulfillment, Order
from shopman.payments.models import PaymentIntent

from shop.models import Promotion, Shop


@pytest.fixture(autouse=True)
def shop_instance(db):
    return Shop.objects.create(
        name="Nelson Boulangerie",
        brand_name="Nelson Boulangerie",
        short_name="Nelson",
        default_ddd="43",
    )


@pytest.fixture
def admin_user(db):
    return User.objects.create_superuser("admin", "admin@test.com", "admin123")


@pytest.fixture
def admin_client(admin_user):
    client = Client()
    client.force_login(admin_user)
    return client


@pytest.fixture
def channel(db):
    return Channel.objects.create(
        ref="web", name="Loja Online", listing_ref="balcao",
        pricing_policy="external", edit_policy="open", config={},
    )


class TestPromotionAdmin:
    def test_promotion_admin_list_displays_status(self, admin_client):
        now = timezone.now()
        Promotion.objects.create(
            name="Ativa", type="percent", value=10,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
        )
        Promotion.objects.create(
            name="Expirada", type="percent", value=5,
            valid_from=now - timedelta(days=10),
            valid_until=now - timedelta(days=1),
        )
        Promotion.objects.create(
            name="Futura", type="fixed", value=500,
            valid_from=now + timedelta(days=1),
            valid_until=now + timedelta(days=10),
        )

        response = admin_client.get("/admin/shop/promotion/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Ativa" in content
        assert "Expirada" in content
        assert "Futura" in content

    def test_promotion_status_filter_ativa(self, admin_client):
        now = timezone.now()
        Promotion.objects.create(
            name="Promo Ativa", type="percent", value=10,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
        )
        Promotion.objects.create(
            name="Promo Expirada", type="percent", value=5,
            valid_from=now - timedelta(days=10),
            valid_until=now - timedelta(days=1),
        )

        response = admin_client.get("/admin/shop/promotion/?situacao=ativa")
        assert response.status_code == 200
        content = response.content.decode()
        assert "Promo Ativa" in content
        assert "Promo Expirada" not in content

    def test_promotion_value_display_percent(self, admin_client):
        now = timezone.now()
        Promotion.objects.create(
            name="Desconto Percent", type="percent", value=15,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=1),
        )

        response = admin_client.get("/admin/shop/promotion/")
        content = response.content.decode()
        assert "15%" in content


class TestCouponAdmin:
    def test_coupon_usage_display_limited(self, admin_client):
        now = timezone.now()
        promo = Promotion.objects.create(
            name="Promo", type="percent", value=10,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
        )
        promo.coupons.create(code="TEST10", max_uses=10, uses_count=3)

        response = admin_client.get("/admin/shop/coupon/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "3/10" in content

    def test_coupon_usage_display_unlimited(self, admin_client):
        now = timezone.now()
        promo = Promotion.objects.create(
            name="Promo", type="percent", value=10,
            valid_from=now - timedelta(days=1),
            valid_until=now + timedelta(days=30),
        )
        promo.coupons.create(code="UNLIMITED", max_uses=0, uses_count=5)

        response = admin_client.get("/admin/shop/coupon/")
        content = response.content.decode()
        assert "ilimitado" in content


class TestOrderAdminInlines:
    def test_order_admin_shows_fulfillment_inline(self, admin_client, channel):
        order = Order.objects.create(
            ref="ORD-F01", channel=channel, status="delivered", total_q=5000,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        Fulfillment.objects.create(
            order=order, status="delivered",
            carrier="correios", tracking_code="BR123456789",
        )

        response = admin_client.get(f"/admin/ordering/order/{order.pk}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "correios" in content
        assert "BR123456789" in content

    def test_order_admin_shows_payment_info(self, admin_client, channel):
        order = Order.objects.create(
            ref="ORD-P01", channel=channel, status="completed", total_q=3500,
            handle_type="phone", handle_ref="5543999990001", data={},
        )
        PaymentIntent.objects.create(
            ref="PAY-001", order_ref="ORD-P01",
            method="pix", status="captured",
            amount_q=3500,
        )

        response = admin_client.get(f"/admin/ordering/order/{order.pk}/change/")
        assert response.status_code == 200
        content = response.content.decode()
        assert "PAY-001" in content
        assert "PIX" in content


class TestDashboardReturns200:
    def test_dashboard_returns_200(self, admin_client):
        response = admin_client.get("/admin/")
        assert response.status_code == 200
