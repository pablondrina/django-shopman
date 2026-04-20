"""Tests for /health/ and /ready/ endpoints."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest
from django.test import Client, override_settings
from django.urls import reverse


@pytest.fixture
def client():
    return Client()


# ── /health/ ────────────────────────────────────────────────────────


def test_health_ok(client, db):
    """Happy path: DB reachable, LocMem cache skipped, no pending migrations."""
    response = client.get(reverse("health"))

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["status"] == "ok"
    assert payload["checks"]["database"] == "ok"
    assert payload["checks"]["cache"] == "skipped"  # LocMem in dev
    assert payload["checks"]["migrations"] == "ok"


def test_health_503_when_db_down(client, db):
    """DB connection failure → 503 with details."""
    with patch(
        "shopman.shop.views.health._check_database",
        return_value=("fail", "OperationalError"),
    ):
        response = client.get(reverse("health"))

    assert response.status_code == 503
    payload = json.loads(response.content)
    assert payload["status"] == "error"
    assert payload["checks"]["database"].startswith("fail")
    assert "OperationalError" in payload["checks"]["database"]


def test_health_200_when_migrations_pending(client, db):
    """Pending migrations reported but non-critical for /health/ (k8s liveness)."""
    with patch(
        "shopman.shop.views.health._check_migrations",
        return_value=("fail", "3 pending"),
    ):
        response = client.get(reverse("health"))

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["status"] == "ok"
    assert payload["checks"]["migrations"].startswith("fail")


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        }
    }
)
def test_health_cache_not_skipped_when_real_backend(client, db):
    """Non-LocMem backends are exercised; DummyCache set/get returns None → fail."""
    response = client.get(reverse("health"))

    assert response.status_code == 503
    payload = json.loads(response.content)
    assert payload["checks"]["cache"].startswith("fail")


# ── /ready/ ─────────────────────────────────────────────────────────


def test_ready_ok(client, db):
    response = client.get(reverse("ready"))

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["status"] == "ok"
    assert payload["checks"]["database"] == "ok"
    assert payload["checks"]["migrations"] == "ok"


def test_ready_503_when_migrations_pending(client, db):
    """Pending migrations → 503 on /ready/ (blocks deploy / k8s readiness)."""
    with patch(
        "shopman.shop.views.health._check_migrations",
        return_value=("fail", "2 pending"),
    ):
        response = client.get(reverse("ready"))

    assert response.status_code == 503
    payload = json.loads(response.content)
    assert payload["status"] == "error"
    assert "2 pending" in payload["checks"]["migrations"]


def test_ready_503_when_db_down(client, db):
    with patch(
        "shopman.shop.views.health._check_database",
        return_value=("fail", "OperationalError"),
    ):
        response = client.get(reverse("ready"))

    assert response.status_code == 503


# ── Invariants ─────────────────────────────────────────────────────


def test_health_no_csrf_required(client, db):
    """POST without CSRF token still gets through (GET-only endpoint → 405)."""
    response = client.post(reverse("health"))
    # Endpoint is GET-only, so expect 405 not 403 — proving CSRF didn't fire.
    assert response.status_code == 405


def test_health_fast_p95(client, db):
    """p95 < 500ms invariant — 20 requests sample."""
    timings = []
    for _ in range(20):
        start = time.perf_counter()
        client.get(reverse("health"))
        timings.append(time.perf_counter() - start)
    timings.sort()
    p95 = timings[int(len(timings) * 0.95) - 1]
    assert p95 < 0.5, f"/health/ p95={p95:.3f}s exceeds 500ms budget"


def test_health_response_shape(client, db):
    """Envelope: status + checks dict with named entries."""
    response = client.get(reverse("health"))
    payload = json.loads(response.content)

    assert set(payload.keys()) == {"status", "checks"}
    assert set(payload["checks"].keys()) == {"database", "cache", "migrations"}


def test_ready_response_shape(client, db):
    response = client.get(reverse("ready"))
    payload = json.loads(response.content)

    assert set(payload.keys()) == {"status", "checks"}
    assert set(payload["checks"].keys()) == {"database", "cache", "migrations"}


def test_health_error_never_leaks_stacktrace(client, db):
    """On failure, response body must not contain traceback / module path."""
    with patch(
        "shopman.shop.views.health._check_database",
        return_value=("fail", "OperationalError"),
    ):
        response = client.get(reverse("health"))

    body = response.content.decode()
    assert "Traceback" not in body
    assert "shopman/shop/views/health.py" not in body
