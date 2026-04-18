"""Tests for WP-GAP-12 — /api/v1/ prefix + X-API-Version header.

Versioning é contrato: testes garantem que (a) os endpoints públicos do
storefront vivem sob `/api/v1/`, (b) toda response carimba
`X-API-Version: 1`, e (c) os paths não-versionados antigos retornam 404.
"""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse


@pytest.fixture
def client():
    return Client()


# ── Prefix contract ────────────────────────────────────────────────


@pytest.mark.django_db
def test_api_cart_mounted_at_v1():
    url = reverse("api-cart")
    assert url.startswith("/api/v1/"), url


@pytest.mark.django_db
def test_api_checkout_mounted_at_v1():
    assert reverse("api-checkout").startswith("/api/v1/")


@pytest.mark.django_db
def test_api_catalog_products_mounted_at_v1():
    assert reverse("api-catalog-products").startswith("/api/v1/")


@pytest.mark.django_db
def test_api_availability_mounted_at_v1():
    url = reverse("api-availability", kwargs={"sku": "ANY"})
    assert url.startswith("/api/v1/")


@pytest.mark.django_db
def test_api_geocode_mounted_at_v1():
    assert reverse("api-geocode-reverse").startswith("/api/v1/")


@pytest.mark.django_db
def test_api_tracking_mounted_at_v1():
    url = reverse("api-tracking", kwargs={"ref": "ABC"})
    assert url.startswith("/api/v1/")


@pytest.mark.django_db
def test_api_account_mounted_at_v1():
    assert reverse("api-account-profile").startswith("/api/v1/")
    assert reverse("api-account-addresses").startswith("/api/v1/")
    assert reverse("api-account-orders").startswith("/api/v1/")


# ── X-API-Version header ────────────────────────────────────────────


@pytest.mark.django_db
def test_v1_response_stamps_x_api_version(client):
    """Every /api/v1/ response must carry X-API-Version: 1."""
    # Cart endpoint: public, no auth required, always 200.
    resp = client.get("/api/v1/cart/")
    assert resp["X-API-Version"] == "1"


@pytest.mark.django_db
def test_non_api_response_does_not_carry_header(client):
    """Non-API responses must NOT carry X-API-Version."""
    resp = client.get("/health/")
    assert "X-API-Version" not in resp


@pytest.mark.django_db
def test_webhooks_do_not_carry_api_version_header(client):
    """Webhooks live outside the versioned API surface."""
    # Hit any webhook path; we only care about absence of the header,
    # not the response code (which may be 400/401/404 depending on path).
    resp = client.post("/api/webhooks/efi/pix/")
    assert "X-API-Version" not in resp


# ── Old unversioned paths are gone ──────────────────────────────────


@pytest.mark.django_db
def test_legacy_api_cart_returns_404(client):
    """`/api/cart/` (no version) must 404 — there is no unversioned surface."""
    resp = client.get("/api/cart/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_legacy_api_checkout_returns_404(client):
    resp = client.post("/api/checkout/", data={}, content_type="application/json")
    assert resp.status_code == 404
