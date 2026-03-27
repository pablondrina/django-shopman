"""Tests for storefront coupon UX (WP-P3)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from shop.models import Coupon, Promotion

pytestmark = pytest.mark.django_db


@pytest.fixture
def promotion(db):
    """Promotion tied to a coupon — NOT auto-applied (has coupons linked)."""
    now = timezone.now()
    return Promotion.objects.create(
        name="Promo Teste",
        type="percent",
        value=10,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=30),
        is_active=True,
    )


@pytest.fixture
def coupon(promotion):
    return Coupon.objects.create(
        code="TESTE10",
        promotion=promotion,
        max_uses=0,
        is_active=True,
    )


@pytest.fixture
def expired_promotion(db):
    now = timezone.now()
    return Promotion.objects.create(
        name="Promo Expirada",
        type="percent",
        value=5,
        valid_from=now - timedelta(days=60),
        valid_until=now - timedelta(days=1),
        is_active=True,
    )


@pytest.fixture
def expired_coupon(expired_promotion):
    return Coupon.objects.create(
        code="EXPIRADO",
        promotion=expired_promotion,
        max_uses=0,
        is_active=True,
    )


# ── Cart shows coupon input ──────────────────────────────────────────


class TestCartShowsCouponInput:
    def test_cart_shows_coupon_input_field(self, cart_session):
        resp = cart_session.get("/cart/")
        content = resp.content.decode()
        assert resp.status_code == 200
        assert 'name="code"' in content
        assert "Aplicar" in content


# ── Apply coupon ─────────────────────────────────────────────────────


class TestApplyCoupon:
    def test_apply_valid_coupon_refreshes_page(self, cart_session, coupon):
        resp = cart_session.post("/cart/coupon/", {"code": "TESTE10"})
        assert resp.status_code == 200
        assert resp.headers.get("HX-Refresh") == "true"

    def test_apply_valid_coupon_stores_in_session(self, cart_session, coupon):
        from shopman.ordering.models import Session

        cart_session.post("/cart/coupon/", {"code": "TESTE10"})
        sk = cart_session.session["cart_session_key"]
        session = Session.objects.get(session_key=sk)
        assert session.data.get("coupon_code") == "TESTE10"

    def test_apply_invalid_coupon_shows_error_message(self, cart_session):
        resp = cart_session.post("/cart/coupon/", {"code": "INVALIDO"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "encontrado" in content.lower() or "inválido" in content.lower()

    def test_apply_expired_coupon_shows_error(self, cart_session, expired_coupon):
        resp = cart_session.post("/cart/coupon/", {"code": "EXPIRADO"})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "expirado" in content.lower()

    def test_apply_empty_code_shows_error(self, cart_session):
        resp = cart_session.post("/cart/coupon/", {"code": ""})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Informe" in content


# ── Remove coupon ────────────────────────────────────────────────────


class TestRemoveCoupon:
    def test_remove_coupon_refreshes_page(self, cart_session, coupon):
        cart_session.post("/cart/coupon/", {"code": "TESTE10"})
        resp = cart_session.post("/cart/coupon/remove/")
        assert resp.status_code == 200
        assert resp.headers.get("HX-Refresh") == "true"

    def test_remove_coupon_clears_session_data(self, cart_session, coupon):
        from shopman.ordering.models import Session

        cart_session.post("/cart/coupon/", {"code": "TESTE10"})
        cart_session.post("/cart/coupon/remove/")
        sk = cart_session.session["cart_session_key"]
        session = Session.objects.get(session_key=sk)
        assert not session.data.get("coupon_code")


# ── Breakdown ────────────────────────────────────────────────────────


class TestCartBreakdown:
    def test_cart_breakdown_with_discount(self, cart_session, coupon):
        from shopman.ordering.models import Session

        cart_session.post("/cart/coupon/", {"code": "TESTE10"})
        sk = cart_session.session["cart_session_key"]
        session = Session.objects.get(session_key=sk)
        # Coupon was stored in session
        assert session.data.get("coupon_code") == "TESTE10"
        # Cart page renders successfully
        resp = cart_session.get("/cart/")
        assert resp.status_code == 200

    def test_cart_breakdown_without_discount(self, cart_session):
        resp = cart_session.get("/cart/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Desconto" not in content

    def test_checkout_shows_readonly_breakdown(self, cart_session, coupon, customer):
        from shopman.auth.protocols.customer import AuthCustomerInfo
        from shopman.auth.services._user_bridge import get_or_create_user_for_customer

        info = AuthCustomerInfo(uuid=customer.uuid, name=customer.name, phone=customer.phone, email=None, is_active=True)
        user, _ = get_or_create_user_for_customer(info)
        cart_session.force_login(user, backend="shopman.auth.backends.PhoneOTPBackend")

        cart_session.post("/cart/coupon/", {"code": "TESTE10"})
        resp = cart_session.get("/checkout/")
        assert resp.status_code == 200
        content = resp.content.decode()
        # Checkout shows order summary but no coupon input form
        assert "Total" in content
        assert 'name="code"' not in content
