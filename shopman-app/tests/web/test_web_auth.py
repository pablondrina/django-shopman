"""Tests for storefront auth views: CustomerLookupView, RequestCodeView, VerifyCodeView."""
from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


# ── CustomerLookupView ────────────────────────────────────────────────


class TestCustomerLookupView:
    def test_lookup_no_phone(self, client: Client):
        resp = client.get("/checkout/customer-lookup/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    def test_lookup_invalid_phone(self, client: Client):
        resp = client.get("/checkout/customer-lookup/?phone=bad")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    def test_lookup_not_found(self, client: Client):
        resp = client.get("/checkout/customer-lookup/?phone=43999998888")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is False

    def test_lookup_found(self, client: Client, customer):
        resp = client.get(f"/checkout/customer-lookup/?phone={customer.phone}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["found"] is True
        assert data["name"] == "João Silva"

    def test_lookup_returns_addresses(self, client: Client, customer, customer_address):
        resp = client.get(f"/checkout/customer-lookup/?phone={customer.phone}")
        data = resp.json()
        assert data["found"] is True
        assert len(data["addresses"]) == 1
        assert data["addresses"][0]["is_default"] is True

    def test_lookup_verified_session(self, client: Client, customer):
        session = client.session
        session["storefront_verified_phone"] = customer.phone
        session.save()
        resp = client.get(f"/checkout/customer-lookup/?phone={customer.phone}")
        data = resp.json()
        assert data["is_verified"] is True


# ── RequestCodeView ───────────────────────────────────────────────────


class TestRequestCodeView:
    def test_request_code_no_phone(self, client: Client):
        resp = client.post("/checkout/request-code/", {"phone": ""})
        assert resp.status_code == 200

    def test_request_code_requires_post(self, client: Client):
        resp = client.get("/checkout/request-code/")
        assert resp.status_code == 405


# ── VerifyCodeView ────────────────────────────────────────────────────


class TestVerifyCodeView:
    def test_verify_code_no_data(self, client: Client):
        resp = client.post("/checkout/verify-code/", {})
        assert resp.status_code == 200

    def test_verify_code_requires_post(self, client: Client):
        resp = client.get("/checkout/verify-code/")
        assert resp.status_code == 405
