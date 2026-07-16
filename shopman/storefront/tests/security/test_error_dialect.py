"""Category 8 — canonical error dialect and no server-internals leakage.

Contract (docs/reference/errors.md):
- Every JSON error carries a human ``detail`` string.
- Field errors add ``field`` and/or ``errors`` (map of field → [messages]).
- **Simple errors, and every 404, speak ONLY the canonical shape**
  ``{detail, field, errors}`` — a 404 never carries ``title`` or ``error_code``.
- DRF serializer failures are converted to the canonical shape (the raw
  ``{"field": [...]}`` never reaches the client).
- No error body leaks a traceback, source path, or SQL.
"""
from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.django_db

CANONICAL_KEYS = {"detail", "field", "errors"}
LEAK_MARKERS = ("Traceback", 'File "', ".py\"", "/Users/", "psycopg", "sqlite3", "SELECT ", "django.db")


def _assert_no_leak(resp) -> None:
    raw = resp.content.decode("utf-8", "replace")
    for marker in LEAK_MARKERS:
        assert marker not in raw, f"error body leaked internals ({marker!r}): {raw[:300]}"


def _body(resp) -> dict:
    try:
        return resp.json()
    except Exception:  # pragma: no cover - a JSON error must be JSON
        pytest.fail(f"error response was not JSON: {resp.content[:200]!r}")


# ── 404s speak only the canonical shape ────────────────────────────────────

NOTFOUND_ENDPOINTS = [
    ("get", "/api/v1/catalog/products/NOPE-SKU/"),
    ("get", "/api/v1/storefront/products/NOPE-SKU/"),
    ("get", "/api/v1/orders/NOPE-REF/confirmation/"),
]


@pytest.mark.parametrize("method,url", NOTFOUND_ENDPOINTS)
def test_404_is_canonical_only(client, method, url):
    """A 404 body carries ``detail`` and no keys beyond the canonical set — no
    ``title``, no ``error_code`` (those belong only to recovery-rich responses)."""
    resp = getattr(client, method)(url)
    assert resp.status_code == 404
    body = _body(resp)
    assert isinstance(body.get("detail"), str) and body["detail"].strip()
    extra = set(body) - CANONICAL_KEYS
    assert not extra, f"404 leaked non-canonical keys {extra} on {url}: {body}"
    assert "title" not in body
    _assert_no_leak(resp)


def test_order_404_is_canonical_only(attacker, order):
    """The order-access 404 (non-owner) is canonical-only — no oracle metadata."""
    resp = attacker.get(f"/api/v1/tracking/{order.ref}/")
    assert resp.status_code == 404
    body = _body(resp)
    assert isinstance(body.get("detail"), str)
    assert set(body) - CANONICAL_KEYS == set(), f"non-canonical 404 keys: {body}"


# ── 401 carries detail ─────────────────────────────────────────────────────


def test_401_has_detail(attacker):
    resp = attacker.get("/api/v1/account/profile/")
    assert resp.status_code == 401
    assert isinstance(_body(resp).get("detail"), str)
    _assert_no_leak(resp)


# ── DRF serializer failure → canonical field error ─────────────────────────


def test_serializer_error_is_canonicalized(cart_session):
    """A missing required field must be converted by the custom EXCEPTION_HANDLER
    into ``{detail, field, errors}`` — the raw DRF ``{"name": [...]}`` never
    reaches the client."""
    resp = cart_session.post(
        "/api/v1/checkout/",
        data=json.dumps({"phone": "+5543999990001", "fulfillment_type": "pickup"}),  # no name
        content_type="application/json",
    )
    assert resp.status_code == 400
    body = _body(resp)
    assert isinstance(body.get("detail"), str) and body["detail"].strip()
    # Canonical field routing present, and NOT the raw DRF list-under-field shape.
    assert "field" in body or "errors" in body
    assert not isinstance(body.get("name"), list), f"raw DRF error leaked: {body}"
    _assert_no_leak(resp)


def test_business_400_has_field_and_errors(cart_session):
    """A business validation error (checkout requiring a date) carries the field
    router and the errors map for inline rendering."""
    resp = cart_session.post(
        "/api/v1/checkout/",
        data=json.dumps({
            "name": "Ana", "phone": "+5543999990001",
            "fulfillment_type": "delivery", "delivery_address": "Rua X 1",
            # no delivery_date → triggers "Escolha a data."
        }),
        content_type="application/json",
    )
    assert resp.status_code == 400
    body = _body(resp)
    assert body.get("detail")
    assert body.get("field") == "delivery_date" or "delivery_date" in (body.get("errors") or {})
    _assert_no_leak(resp)


# ── Rate-limit 429 shape (recovery superset is allowed, detail still required) ─


def test_rate_limit_429_still_has_detail(client):
    """A 429 may carry the recovery superset, but ``detail`` remains mandatory
    and nothing leaks."""
    from unittest.mock import patch

    from django.core.cache import cache
    from django.test import override_settings

    cache.clear()
    with override_settings(RATELIMIT_ENABLE=True), patch(
        "django_ratelimit.core._get_window", return_value=2_000_000_000
    ):
        last = None
        for _ in range(122):
            last = client.get("/api/v1/tracking/NOPE-REF/")
            if last.status_code == 429:
                break
    cache.clear()
    assert last is not None and last.status_code == 429
    body = _body(last)
    assert isinstance(body.get("detail"), str) and body["detail"].strip()
    assert body.get("error_code") == "rate_limited"
    _assert_no_leak(last)
