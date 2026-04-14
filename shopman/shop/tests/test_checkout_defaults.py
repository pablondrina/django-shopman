"""
Tests for WP-R7 — Checkout Defaults Pre-fill.

Covers:
- Authenticated customer with saved defaults sees them in context
- New customer sees empty defaults
- checkout_defaults passed to template context
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


def _setup_channel():
    from shopman.shop.models import Channel
    return Channel.objects.get_or_create(
        ref="web",
        defaults={
            "name": "Web",
            "is_active": True,
        },
    )[0]


def _setup_product():
    from shopman.offerman.models import Product
    return Product.objects.get_or_create(
        sku="DEFAULT-SKU",
        defaults={
            "name": "Test Product",
            "base_price_q": 1000,
            "is_published": True,
            "is_sellable": True,
        },
    )[0]


def _add_to_cart(client):
    product = _setup_product()
    with patch("shopman.shop.services.availability.reserve", return_value={
        "ok": True, "hold_id": "fake-hold", "available_qty": 999,
        "is_paused": False, "error_code": None, "alternatives": [],
    }):
        client.post("/cart/add/", {"sku": product.sku, "qty": "1"})


def _login_as_customer(client, customer):
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=getattr(customer, "full_name", "") or getattr(customer, "first_name", ""),
        phone=customer.phone,
        email=None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


class TestCheckoutDefaultsContext:
    """CheckoutView GET passes checkout_defaults to template context."""

    @pytest.fixture(autouse=True)
    def setup(self, db):
        from shopman.shop.models import Shop
        Shop.objects.get_or_create(name="Test Shop", defaults={"brand_name": "Test"})
        _setup_channel()
        _setup_product()

    def test_new_customer_gets_empty_defaults(self, client: Client):
        """Customer with no prior orders sees empty checkout_defaults."""
        from shopman.guestman.models import Customer

        customer = Customer.objects.create(
            first_name="New",
            last_name="Customer",
            phone="5543999990011",
        )
        _login_as_customer(client, customer)
        _add_to_cart(client)

        with patch("shopman.shop.services.checkout_defaults.CheckoutDefaultsService.get_defaults") as mock_get:
            mock_get.return_value = {}
            resp = client.get("/checkout/")

        assert resp.status_code == 200
        assert resp.context["checkout_defaults"] == {}

    def test_returning_customer_gets_defaults(self, client: Client):
        """Customer with saved defaults sees them in checkout context."""
        from shopman.guestman.models import Customer

        customer = Customer.objects.create(
            first_name="Returning",
            last_name="Customer",
            phone="5543999990022",
        )
        _login_as_customer(client, customer)
        _add_to_cart(client)

        saved_defaults = {
            "fulfillment_type": "pickup",
            "payment_method": "dinheiro",
        }
        with patch("shopman.shop.services.checkout_defaults.CheckoutDefaultsService.get_defaults") as mock_get:
            mock_get.return_value = saved_defaults
            resp = client.get("/checkout/")

        assert resp.status_code == 200
        assert resp.context["checkout_defaults"]["fulfillment_type"] == "pickup"
        assert resp.context["checkout_defaults"]["payment_method"] == "dinheiro"

    def test_checkout_defaults_service_called_with_customer_ref(self, client: Client):
        """CheckoutDefaultsService.get_defaults is called with the right customer ref."""
        from shopman.guestman.models import Customer

        customer = Customer.objects.create(
            first_name="Test",
            last_name="Customer",
            phone="5543999990033",
        )
        _login_as_customer(client, customer)
        _add_to_cart(client)

        with patch("shopman.shop.services.checkout_defaults.CheckoutDefaultsService.get_defaults") as mock_get:
            mock_get.return_value = {}
            resp = client.get("/checkout/")

        assert resp.status_code == 200
        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args
        assert call_kwargs.kwargs.get("channel_ref") == "web" or (
            len(call_kwargs.args) >= 2 and call_kwargs.args[1] == "web"
        )

    def test_defaults_failure_does_not_break_checkout(self, client: Client):
        """If get_defaults raises, checkout still renders with empty defaults."""
        from shopman.guestman.models import Customer

        customer = Customer.objects.create(
            first_name="Error",
            last_name="Customer",
            phone="5543999990044",
        )
        _login_as_customer(client, customer)
        _add_to_cart(client)

        with patch("shopman.shop.services.checkout_defaults.CheckoutDefaultsService.get_defaults") as mock_get:
            mock_get.side_effect = Exception("DB error")
            resp = client.get("/checkout/")

        assert resp.status_code == 200
        assert resp.context["checkout_defaults"] == {}
