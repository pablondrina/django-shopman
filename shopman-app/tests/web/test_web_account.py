"""Tests for storefront account views: AccountView, Address CRUD views."""
from __future__ import annotations

import pytest
from django.test import Client
from shopman.customers.models import CustomerAddress

pytestmark = pytest.mark.django_db


# ── AccountView GET ───────────────────────────────────────────────────


class TestAccountViewGet:
    def test_account_page_no_session(self, client: Client):
        resp = client.get("/minha-conta/")
        assert resp.status_code == 200

    def test_account_page_with_verified_session(self, client: Client, customer):
        session = client.session
        session["storefront_verified_phone"] = customer.phone
        session.save()
        resp = client.get("/minha-conta/")
        assert resp.status_code == 200


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

    def test_lookup_customer_found(self, client: Client, customer):
        resp = client.post("/minha-conta/", {"phone": "43999990001"})
        assert resp.status_code == 200
        assert "Silva" in resp.content.decode()

    def test_lookup_shows_orders(self, client: Client, customer, order):
        resp = client.post("/minha-conta/", {"phone": customer.phone})
        assert resp.status_code == 200

    def test_lookup_shows_addresses(self, client: Client, customer, customer_address):
        resp = client.post("/minha-conta/", {"phone": customer.phone})
        assert resp.status_code == 200
        assert b"Flores" in resp.content


# ── AddressCreateView ─────────────────────────────────────────────────


class TestAddressCreateView:
    def test_create_address(self, client: Client, customer):
        resp = client.post("/minha-conta/enderecos/", {
            "customer_phone": customer.phone,
            "label": "work",
            "formatted_address": "Av Brasil 500 - Centro - Londrina",
            "city": "Londrina",
        })
        assert resp.status_code == 200
        assert CustomerAddress.objects.filter(customer=customer).count() == 1

    def test_create_address_no_phone(self, client: Client):
        resp = client.post("/minha-conta/enderecos/", {
            "formatted_address": "Rua X",
        })
        assert resp.status_code == 400

    def test_create_address_invalid_phone(self, client: Client):
        resp = client.post("/minha-conta/enderecos/", {
            "customer_phone": "bad",
            "formatted_address": "Rua X",
        })
        assert resp.status_code in (400, 404)  # 400 if normalize raises, 404 if customer not found

    def test_create_address_unknown_customer(self, client: Client):
        resp = client.post("/minha-conta/enderecos/", {
            "customer_phone": "5543999998888",
            "formatted_address": "Rua X",
        })
        assert resp.status_code == 404

    def test_create_address_empty_address(self, client: Client, customer):
        resp = client.post("/minha-conta/enderecos/", {
            "customer_phone": customer.phone,
            "label": "home",
        })
        assert resp.status_code == 200  # re-renders form with errors

    def test_create_address_builds_from_components(self, client: Client, customer):
        resp = client.post("/minha-conta/enderecos/", {
            "customer_phone": customer.phone,
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
    def test_update_address(self, client: Client, customer, customer_address):
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/", {
            "customer_phone": customer.phone,
            "formatted_address": "Av Nova 789",
        })
        assert resp.status_code == 200
        customer_address.refresh_from_db()
        assert "Nova" in customer_address.formatted_address

    def test_update_address_wrong_phone(self, client: Client, customer, customer_address):
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/", {
            "customer_phone": "5543888887777",
            "formatted_address": "Rua X",
        })
        assert resp.status_code == 403

    def test_update_address_not_found(self, client: Client):
        resp = client.post("/minha-conta/enderecos/99999/", {
            "formatted_address": "Rua X",
        })
        assert resp.status_code == 404


# ── AddressDeleteView ─────────────────────────────────────────────────


class TestAddressDeleteView:
    def test_delete_address(self, client: Client, customer, customer_address):
        pk = customer_address.pk
        resp = client.post(f"/minha-conta/enderecos/{pk}/delete/", {
            "customer_phone": customer.phone,
        })
        assert resp.status_code == 200
        assert not CustomerAddress.objects.filter(pk=pk).exists()

    def test_delete_address_wrong_phone(self, client: Client, customer, customer_address):
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/delete/", {
            "customer_phone": "5543888887777",
        })
        assert resp.status_code == 403

    def test_delete_address_not_found(self, client: Client):
        resp = client.post("/minha-conta/enderecos/99999/delete/")
        assert resp.status_code == 404


# ── AddressSetDefaultView ─────────────────────────────────────────────


class TestAddressSetDefaultView:
    def test_set_default(self, client: Client, customer, customer_address):
        second = CustomerAddress.objects.create(
            customer=customer, label="work",
            formatted_address="Av X 1", is_default=False,
        )
        resp = client.post(f"/minha-conta/enderecos/{second.pk}/default/", {
            "customer_phone": customer.phone,
        })
        assert resp.status_code == 200
        second.refresh_from_db()
        assert second.is_default

    def test_set_default_wrong_phone(self, client: Client, customer, customer_address):
        resp = client.post(f"/minha-conta/enderecos/{customer_address.pk}/default/", {
            "customer_phone": "5543888887777",
        })
        assert resp.status_code == 403

    def test_set_default_not_found(self, client: Client):
        resp = client.post("/minha-conta/enderecos/99999/default/")
        assert resp.status_code == 404
