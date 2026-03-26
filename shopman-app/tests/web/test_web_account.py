"""Tests for storefront account views: AccountView, Address CRUD views.

Security model: all account data and address operations require
Django auth via OTP verification.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from shopman.customers.models import CustomerAddress

pytestmark = pytest.mark.django_db


def _login_as_customer(client: Client, customer) -> User:
    """Log in the Django test client as a customer via Django auth."""
    from shopman.auth.protocols.customer import AuthCustomerInfo
    from shopman.auth.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.auth.backends.PhoneOTPBackend")
    return user


# ── AccountView GET ───────────────────────────────────────────────────


class TestAccountViewGet:
    def test_account_page_no_session(self, client: Client):
        resp = client.get("/minha-conta/")
        assert resp.status_code == 200
        assert resp.context["customer"] is None

    def test_account_page_with_verified_session(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.get("/minha-conta/")
        assert resp.status_code == 200
        assert resp.context["customer"] is not None
        assert resp.context["customer"].pk == customer.pk


# ── AccountView POST ──────────────────────────────────────────────────


class TestAccountViewPost:
    def test_lookup_missing_phone(self, client: Client):
        resp = client.post("/minha-conta/", {"phone": ""})
        assert resp.status_code == 200
        assert "obrigat" in resp.content.decode().lower()

    def test_lookup_invalid_phone(self, client: Client):
        resp = client.post("/minha-conta/", {"phone": "123"})
        assert resp.status_code == 200
        assert "inv" in resp.content.decode().lower()

    def test_lookup_customer_not_found(self, client: Client):
        resp = client.post("/minha-conta/", {"phone": "43999998888"})
        assert resp.status_code == 200

    def test_lookup_requires_verification(self, client: Client, customer):
        """POST with valid phone but no auth shows verification prompt, NOT data."""
        resp = client.post("/minha-conta/", {"phone": "43999990001"})
        assert resp.status_code == 200
        assert resp.context.get("needs_verification") is True
        assert resp.context["customer"] is None
        content = resp.content.decode()
        assert "Confirme sua identidade" in content
        # Must NOT show sensitive data
        assert "Enderecos" not in content
        assert "Ultimos pedidos" not in content

    def test_lookup_with_verified_session_shows_data(self, client: Client, customer):
        """POST with valid phone AND authenticated shows data."""
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/", {"phone": customer.phone})
        assert resp.status_code == 200
        assert resp.context["customer"] is not None

    def test_lookup_shows_orders_when_verified(self, client: Client, customer, order):
        _login_as_customer(client, customer)
        resp = client.get("/minha-conta/")
        assert resp.status_code == 200

    def test_lookup_shows_addresses_when_verified(self, client: Client, customer, customer_address):
        _login_as_customer(client, customer)
        resp = client.get("/minha-conta/")
        assert resp.status_code == 200
        assert b"Flores" in resp.content


# ── AddressCreateView ─────────────────────────────────────────────────


class TestAddressCreateView:
    def test_create_address_requires_auth(self, client: Client, customer):
        """Address creation without auth returns 401."""
        resp = client.post("/minha-conta/enderecos/", {
            "label": "work",
            "formatted_address": "Av Brasil 500 - Centro - Londrina",
        })
        assert resp.status_code == 401

    def test_create_address_with_session(self, client: Client, customer):
        """Address creation WITH auth succeeds."""
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/enderecos/", {
            "label": "work",
            "formatted_address": "Av Brasil 500 - Centro - Londrina",
            "city": "Londrina",
        })
        assert resp.status_code == 200
        assert CustomerAddress.objects.filter(customer=customer).count() == 1

    def test_create_address_empty_address(self, client: Client, customer):
        """Empty address re-renders form with errors."""
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/enderecos/", {
            "label": "home",
        })
        assert resp.status_code == 200  # re-renders form with errors

    def test_create_address_builds_from_components(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/enderecos/", {
            "route": "Rua Nova",
            "street_number": "456",
            "neighborhood": "Vila A",
            "city": "Londrina",
        })
        assert resp.status_code == 200
        addr = CustomerAddress.objects.filter(customer=customer).first()
        assert addr is not None
        assert "Rua Nova" in addr.formatted_address


# ── AddressUpdateView ─────────────────────────────────────────────────


class TestAddressUpdateView:
    def test_update_address_requires_auth(self, client: Client, customer_address):
        """Update without auth returns 401."""
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/", {
            "formatted_address": "Av Nova 789",
        })
        assert resp.status_code == 401

    def test_update_address_with_session(self, client: Client, customer, customer_address):
        """Update WITH auth succeeds."""
        _login_as_customer(client, customer)
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/", {
            "formatted_address": "Av Nova 789",
        })
        assert resp.status_code == 200
        customer_address.refresh_from_db()
        assert "Nova" in customer_address.formatted_address

    def test_update_address_wrong_customer(self, client: Client, customer, customer_address):
        """Authenticated user cannot update another customer's address."""
        from shopman.customers.models import Customer

        other = Customer.objects.create(
            ref="OTHER-001", first_name="Pedro", phone="5543888880001",
        )
        _login_as_customer(client, other)
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/", {
            "formatted_address": "Rua X",
        })
        assert resp.status_code == 403

    def test_update_address_not_found(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/enderecos/99999/", {
            "formatted_address": "Rua X",
        })
        assert resp.status_code == 404


# ── AddressDeleteView ─────────────────────────────────────────────────


class TestAddressDeleteView:
    def test_delete_address_requires_auth(self, client: Client, customer_address):
        """Delete without auth returns 401."""
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/delete/")
        assert resp.status_code == 401

    def test_delete_address_with_session(self, client: Client, customer, customer_address):
        """Delete WITH auth succeeds."""
        _login_as_customer(client, customer)
        pk = customer_address.pk
        resp = client.post(f"/minha-conta/enderecos/{pk}/delete/")
        assert resp.status_code == 200
        assert not CustomerAddress.objects.filter(pk=pk).exists()

    def test_delete_address_wrong_customer(self, client: Client, customer, customer_address):
        """Authenticated user cannot delete another customer's address."""
        from shopman.customers.models import Customer

        other = Customer.objects.create(
            ref="OTHER-002", first_name="Pedro", phone="5543888880002",
        )
        _login_as_customer(client, other)
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/delete/")
        assert resp.status_code == 403

    def test_delete_address_not_found(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/enderecos/99999/delete/")
        assert resp.status_code == 404


# ── AddressSetDefaultView ─────────────────────────────────────────────


class TestAddressSetDefaultView:
    def test_set_default_requires_auth(self, client: Client, customer_address):
        """Set default without auth returns 401."""
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/default/")
        assert resp.status_code == 401

    def test_set_default_with_session(self, client: Client, customer, customer_address):
        """Set default WITH auth succeeds."""
        _login_as_customer(client, customer)
        second = CustomerAddress.objects.create(
            customer=customer, label="work",
            formatted_address="Av X 1", is_default=False,
        )
        resp = client.post(f"/minha-conta/enderecos/{second.pk}/default/")
        assert resp.status_code == 200
        second.refresh_from_db()
        assert second.is_default

    def test_set_default_wrong_customer(self, client: Client, customer, customer_address):
        """Authenticated user cannot set default on another customer's address."""
        from shopman.customers.models import Customer

        other = Customer.objects.create(
            ref="OTHER-003", first_name="Pedro", phone="5543888880003",
        )
        _login_as_customer(client, other)
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/default/")
        assert resp.status_code == 403

    def test_set_default_not_found(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/enderecos/99999/default/")
        assert resp.status_code == 404
