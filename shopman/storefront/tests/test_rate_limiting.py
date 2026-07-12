"""Rate limiting on the storefront API endpoints the BFF consumes.

OTP request/verify, checkout, tracking polling, reorder and cart mutation all
return a recovery payload (error_code + retry_after_seconds + Retry-After) so the
Nuxt store can surface a friendly wait instead of a bare 429.
"""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear Django cache before/after each test to reset rate limit counters."""
    cache.clear()
    with patch("django_ratelimit.core._get_window", return_value=2_000_000_000):
        yield
    cache.clear()


# ── OTP request / verify (api/auth) ────────────────────────────────────────


@override_settings(RATELIMIT_ENABLE=True)
def test_api_otp_request_rate_limited(client: Client):
    """6th OTP request in the same minute returns 429."""
    payload = json.dumps({"phone": "+5511999990001"})
    for _ in range(5):
        resp = client.post("/api/v1/auth/request-code/", data=payload, content_type="application/json")
        assert resp.status_code != 429, f"not limited before 5 (got {resp.status_code})"

    resp = client.post("/api/v1/auth/request-code/", data=payload, content_type="application/json")
    assert resp.status_code == 429


@override_settings(RATELIMIT_ENABLE=True)
def test_otp_rate_limit_is_per_client_ip_not_shared_proxy_bucket(client: Client):
    """Atrás do load balancer, dois clientes têm o MESMO REMOTE_ADDR (o proxy).
    O rate-limit deve isolar por IP real (X-Forwarded-For), senão um cliente
    agressivo esgota o limite e bloqueia OTP/login de toda a loja.
    """
    proxy = "10.0.0.1"  # REMOTE_ADDR compartilhado (o load balancer)

    def _request(*, xff: str):
        return client.post(
            "/api/v1/auth/request-code/",
            data=json.dumps({"phone": "+5511999990010"}),
            content_type="application/json",
            REMOTE_ADDR=proxy,
            HTTP_X_FORWARDED_FOR=xff,
        )

    # Cliente A esgota o limite de 5/min.
    for _ in range(5):
        assert _request(xff="9.9.9.9").status_code != 429
    assert _request(xff="9.9.9.9").status_code == 429  # A bloqueado

    # Cliente B — mesmo proxy, IP real diferente — não é vítima do bloqueio de A.
    assert _request(xff="8.8.8.8").status_code != 429


@override_settings(RATELIMIT_ENABLE=True)
def test_api_otp_verify_rate_limited(client: Client):
    """11th OTP verify in the same minute returns 429."""
    payload = json.dumps({"phone": "+5511999990003", "code": "000000"})
    for _ in range(10):
        resp = client.post("/api/v1/auth/verify-code/", data=payload, content_type="application/json")
        assert resp.status_code != 429, f"not limited before 10 (got {resp.status_code})"

    resp = client.post("/api/v1/auth/verify-code/", data=payload, content_type="application/json")
    assert resp.status_code == 429


# ── Checkout (api/views.CheckoutView) ──────────────────────────────────────


@override_settings(RATELIMIT_ENABLE=True)
def test_api_checkout_invalid_attempts_never_rate_limit(client: Client):
    """Tentativa INVÁLIDA (erro de formulário/carrinho vazio) não conta para o
    limite — cliente corrigindo o form não pode tomar 429 (audit pré-go-live).
    Só a tentativa que passa pelas validações e chega ao commit incrementa."""
    payload = {
        "name": "Test User",
        "phone": "+5511999990007",
        "fulfillment_type": "pickup",
    }
    for _ in range(10):  # bem acima do limite de 3/min
        resp = client.post("/api/v1/checkout/", data=payload, content_type="application/json")
        assert resp.status_code == 400, f"esperava 400 de carrinho vazio, veio {resp.status_code}"


@override_settings(RATELIMIT_ENABLE=True)
def test_api_checkout_normal_use_passes(client: Client):
    """Single API checkout POST is not rate-limited."""
    resp = client.post(
        "/api/v1/checkout/",
        data={"name": "Test", "phone": "+5511999990008", "fulfillment_type": "pickup"},
        content_type="application/json",
    )
    assert resp.status_code != 429


# ── Tracking / reorder / cart mutation (recovery payloads) ─────────────────


@override_settings(RATELIMIT_ENABLE=True)
def test_api_tracking_rate_limited_payload_has_recovery(client: Client):
    """121st tracking poll returns a recovery payload, not a bare 429."""
    for _ in range(120):
        resp = client.get("/api/v1/tracking/NOPE/")
        assert resp.status_code != 429

    resp = client.get("/api/v1/tracking/NOPE/")
    assert resp.status_code == 429
    data = resp.json()
    assert data["error_code"] == "rate_limited"
    assert data["retry_after_seconds"] == 30
    assert resp.headers["Retry-After"] == "30"


@override_settings(RATELIMIT_ENABLE=True)
def test_api_reorder_rate_limited_payload_has_recovery(client: Client):
    """21st reorder attempt returns wait/retry metadata for the Nuxt modal."""
    for _ in range(20):
        resp = client.post("/api/v1/orders/NOPE/reorder/", data={}, content_type="application/json")
        assert resp.status_code != 429

    resp = client.post("/api/v1/orders/NOPE/reorder/", data={}, content_type="application/json")
    assert resp.status_code == 429
    data = resp.json()
    assert data["error_code"] == "rate_limited"
    assert data["retry_after_seconds"] == 60
    assert resp.headers["Retry-After"] == "60"


@override_settings(RATELIMIT_ENABLE=True)
def test_api_cart_sku_qty_rate_limited_payload_has_recovery(client: Client):
    """121st SKU quantity mutation returns wait/retry metadata for the cart modal."""
    payload = json.dumps({"qty": 1})
    for _ in range(120):
        resp = client.put(
            "/api/v1/cart/skus/DOES-NOT-EXIST/",
            data=payload,
            content_type="application/json",
        )
        assert resp.status_code != 429

    resp = client.put(
        "/api/v1/cart/skus/DOES-NOT-EXIST/",
        data=payload,
        content_type="application/json",
    )
    assert resp.status_code == 429
    data = resp.json()
    assert data["error_code"] == "rate_limited"
    assert data["retry_after_seconds"] == 30
    assert resp.headers["Retry-After"] == "30"
