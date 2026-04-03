"""Tests for account views (profile, addresses).

Account requires login — unauthenticated users are redirected to /login/.
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client

from shopman.customers.models import Customer, CustomerAddress

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


# ── AccountView GET ──────────────────────────────────────────────────


class TestAccountViewGet:
    def test_account_redirects_to_login_if_unauthenticated(self, client: Client):
        resp = client.get("/minha-conta/")
        assert resp.status_code == 302
        assert "/login/" in resp.url

    def test_account_page_with_verified_session(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.get("/minha-conta/")
        assert resp.status_code == 200
        assert resp.context["customer"] is not None
        assert resp.context["customer"].pk == customer.pk


# ── AccountView POST ──────────────────────────────────────────────────


class TestAccountViewPost:
    def test_post_redirects_to_login(self, client: Client):
        """POST without auth redirects to login."""
        resp = client.post("/minha-conta/", {"phone": "43999990001"})
        assert resp.status_code == 302
        assert "/login/" in resp.url


# ── Addresses ────────────────────────────────────────────────────────


class TestAddressCreate:
    def test_create_address_requires_auth(self, client: Client):
        resp = client.post("/minha-conta/enderecos/", {
            "formatted_address": "Rua Teste 123",
        })
        assert resp.status_code == 401

    def test_create_address(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/enderecos/", {
            "route": "Rua das Flores",
            "street_number": "123",
            "neighborhood": "Centro",
            "city": "Londrina",
        })
        assert resp.status_code == 200
        assert customer.addresses.count() == 1


class TestAddressDelete:
    def test_delete_requires_ownership(self, client: Client, customer, customer_address):
        """Cannot delete another customer's address."""
        other = Customer.objects.create(ref="OTHER", first_name="Outro", phone="5543888880000")
        _login_as_customer(client, other)
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/delete/")
        assert resp.status_code == 403

    def test_delete_own_address(self, client: Client, customer, customer_address):
        _login_as_customer(client, customer)
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/delete/")
        assert resp.status_code == 200
        assert customer.addresses.count() == 0


class TestAddressSetDefault:
    def test_set_default(self, client: Client, customer, customer_address):
        addr2 = CustomerAddress.objects.create(
            customer=customer, label="work",
            formatted_address="Rua B 456", is_default=False,
        )
        _login_as_customer(client, customer)
        resp = client.post(f"/minha-conta/enderecos/{addr2.pk}/default/")
        assert resp.status_code == 200
        addr2.refresh_from_db()
        assert addr2.is_default is True


# ── Profile ──────────────────────────────────────────────────────────


class TestProfileUpdate:
    def test_update_profile(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/perfil/", {
            "first_name": "Maria",
            "last_name": "Silva",
            "email": "maria@email.com",
        })
        assert resp.status_code == 200
        customer.refresh_from_db()
        assert customer.first_name == "Maria"
        assert customer.email == "maria@email.com"

    def test_update_requires_name(self, client: Client, customer):
        _login_as_customer(client, customer)
        resp = client.post("/minha-conta/perfil/", {"first_name": ""})
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "obrigatório" in content.lower()
