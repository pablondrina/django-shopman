"""Tests for rate limiting on OTP and checkout endpoints.

WP-C3: Rate Limiting (OTP, login, checkout).
"""
from __future__ import annotations

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear Django cache before/after each test to reset rate limit counters."""
    cache.clear()
    yield
    cache.clear()


# ── OTP Request (RequestCodeView) ──────────────────────────────────────────


@override_settings(RATELIMIT_ENABLE=True)
def test_otp_request_rate_limited(client: Client):
    """6th OTP request in the same minute returns 429."""
    payload = {"phone": "+5511999990001"}
    for _ in range(5):
        resp = client.post("/checkout/request-code/", data=payload)
        assert resp.status_code != 429, (
            f"Should not be rate limited before 5 requests (got {resp.status_code})"
        )

    resp = client.post("/checkout/request-code/", data=payload)
    assert resp.status_code == 429


@override_settings(RATELIMIT_ENABLE=True)
def test_otp_request_normal_use_passes(client: Client):
    """Single OTP request is not rate-limited."""
    resp = client.post("/checkout/request-code/", data={"phone": "+5511999990002"})
    assert resp.status_code != 429


# ── OTP Verify (VerifyCodeView) ────────────────────────────────────────────


@override_settings(RATELIMIT_ENABLE=True)
def test_otp_verify_rate_limited(client: Client):
    """11th OTP verify request in the same minute returns 429."""
    payload = {"phone": "+5511999990003", "code": "000000"}
    for _ in range(10):
        resp = client.post("/checkout/verify-code/", data=payload)
        assert resp.status_code != 429, (
            f"Should not be rate limited before 10 requests (got {resp.status_code})"
        )

    resp = client.post("/checkout/verify-code/", data=payload)
    assert resp.status_code == 429


@override_settings(RATELIMIT_ENABLE=True)
def test_otp_verify_normal_use_passes(client: Client):
    """Single OTP verify request is not rate-limited."""
    resp = client.post(
        "/checkout/verify-code/",
        data={"phone": "+5511999990004", "code": "000000"},
    )
    assert resp.status_code != 429


# ── Web Checkout (CheckoutView) ────────────────────────────────────────────


@override_settings(RATELIMIT_ENABLE=True)
def test_checkout_rate_limited(client: Client):
    """4th checkout POST in the same minute returns 429."""
    payload = {
        "name": "Test User",
        "phone": "+5511999990005",
        "fulfillment_type": "pickup",
        "payment_method": "counter",
    }
    for _ in range(3):
        resp = client.post("/checkout/", data=payload)
        assert resp.status_code != 429, (
            f"Should not be rate limited before 3 requests (got {resp.status_code})"
        )

    resp = client.post("/checkout/", data=payload)
    assert resp.status_code == 429


@override_settings(RATELIMIT_ENABLE=True)
def test_checkout_normal_use_passes(client: Client):
    """Single checkout POST is not rate-limited."""
    resp = client.post(
        "/checkout/",
        data={
            "name": "Test User",
            "phone": "+5511999990006",
            "fulfillment_type": "pickup",
            "payment_method": "counter",
        },
    )
    assert resp.status_code != 429


# ── API Checkout (api/views.CheckoutView) ─────────────────────────────────


@override_settings(RATELIMIT_ENABLE=True)
def test_api_checkout_rate_limited(client: Client):
    """4th API checkout POST in the same minute returns 429."""
    payload = {
        "name": "Test User",
        "phone": "+5511999990007",
        "fulfillment_type": "pickup",
    }
    for _ in range(3):
        resp = client.post("/api/checkout/", data=payload, content_type="application/json")
        assert resp.status_code != 429, (
            f"Should not be rate limited before 3 requests (got {resp.status_code})"
        )

    resp = client.post("/api/checkout/", data=payload, content_type="application/json")
    assert resp.status_code == 429


@override_settings(RATELIMIT_ENABLE=True)
def test_api_checkout_normal_use_passes(client: Client):
    """Single API checkout POST is not rate-limited."""
    resp = client.post(
        "/api/checkout/",
        data={"name": "Test", "phone": "+5511999990008", "fulfillment_type": "pickup"},
        content_type="application/json",
    )
    assert resp.status_code != 429
