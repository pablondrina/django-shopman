"""
Playwright E2E — Pytest fixtures (post-headless topology).

The headless cutover split the customer surface from Django: the **Nuxt store**
serves every customer page, and **Django** serves only the API + the operator/
admin pages. So the browser E2E talks to TWO running servers:

  · ``store_base_url``    — the Nuxt customer store (menu/PDP/cart/checkout/
                            tracking/payment).
  · ``operator_base_url`` — Django (admin order console, KDS).

Boot both with the canonical orchestration (mirrors the WP-8 Omotenashi gate),
which also seeds the DB so the order-scoped fixtures resolve:

    scripts/run_storefront_e2e.sh

…or, with both servers already up, point the bases yourself:

    pytest shopman/shop/tests/e2e/test_storefront_e2e.py \\
        --store-base-url=http://127.0.0.1:3100 \\
        --operator-base-url=http://127.0.0.1:8001

Order-scoped store pages (tracking/payment) authorize by **session grant**
(``shopman_order_access_refs``) — DRF does not read ``request.user`` there — so
the fixtures below mint a Django session carrying the grant, exactly like a real
customer's session after checkout/magic-link. The same DB the running servers
use is reached directly via the ORM (the E2E process shares ``config.settings``
→ same database), so the session row is visible to the live server.
"""

from __future__ import annotations

import threading
from urllib.parse import urlparse

import pytest


def _in_thread(fn, *args, **kwargs):
    """Run ``fn`` in a fresh OS thread and return its result.

    The Playwright sync API keeps an event loop running on the test thread, so
    Django's sync ORM raises ``SynchronousOnlyOperation`` if called there. A
    worker thread has no running loop, so DB access is safe.
    """
    box: dict = {}

    def target():
        try:
            box["value"] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller thread
            box["error"] = exc

    thread = threading.Thread(target=target)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]

DEFAULT_STORE_BASE_URL = "http://127.0.0.1:3100"
DEFAULT_OPERATOR_BASE_URL = "http://127.0.0.1:8001"


def pytest_addoption(parser):
    group = parser.getgroup("shopman-e2e", "Shopman storefront E2E")
    group.addoption(
        "--store-base-url",
        action="store",
        default=DEFAULT_STORE_BASE_URL,
        help="Base URL of the running Nuxt customer store",
    )
    group.addoption(
        "--operator-base-url",
        action="store",
        default=DEFAULT_OPERATOR_BASE_URL,
        help="Base URL of the running Django server (API + operator/admin pages)",
    )


@pytest.fixture(scope="session")
def store_base_url(request):
    return request.config.getoption("--store-base-url").rstrip("/")


@pytest.fixture(scope="session")
def operator_base_url(request):
    return request.config.getoption("--operator-base-url").rstrip("/")


# ---------------------------------------------------------------------------
# Seeded scenario refs — reuse the single source of truth (Omotenashi matrix)
# ---------------------------------------------------------------------------


def _qa_checks_by_id(django_db_blocker) -> dict:
    """The seeded Omotenashi QA matrix, keyed by check id.

    Reuses ``build_omotenashi_qa_report`` so the E2E and the browser-QA gate
    resolve the SAME seeded scenarios (READY tracking order, PIX-pending order)
    instead of duplicating seed-key knowledge here.
    """
    with django_db_blocker.unblock():
        from shopman.backstage.services.omotenashi_qa import build_omotenashi_qa_report

        report = build_omotenashi_qa_report()
        return {check.id: check for check in report.checks}


@pytest.fixture(scope="session")
def _qa_checks(django_db_blocker):
    return _in_thread(_qa_checks_by_id, django_db_blocker)


def _ref_or_skip(checks: dict, check_id: str) -> str:
    check = checks.get(check_id)
    ref = getattr(check, "order_ref", "") if check else ""
    if not ref:
        pytest.skip(f"Cenário '{check_id}' ausente no seed — rode make seed.")
    return ref


@pytest.fixture
def ready_order_ref(_qa_checks) -> str:
    """Ref of a seeded READY order (customer tracking)."""
    return _ref_or_skip(_qa_checks, "mobile.tracking.ready")


@pytest.fixture
def pix_pending_order_ref(_qa_checks) -> str:
    """Ref of a seeded PIX-pending order (customer payment)."""
    return _ref_or_skip(_qa_checks, "mobile.payment.pix_pending_near_expiry")


# ---------------------------------------------------------------------------
# Session minting — order-access grant + superuser, set as a browser cookie
# ---------------------------------------------------------------------------


def _mint_session(django_db_blocker, *, order_refs=(), superuser=False) -> dict:
    """Create a Django session row and return its cookie {name, value}.

    ``order_refs`` grants customer order-access (store pages authorize on it);
    ``superuser`` binds an operator identity (admin/order-console pages).
    """
    with django_db_blocker.unblock():
        from django.conf import settings
        from django.contrib.auth import (
            BACKEND_SESSION_KEY,
            HASH_SESSION_KEY,
            SESSION_KEY,
            get_user_model,
        )
        from django.contrib.sessions.backends.db import SessionStore

        from shopman.shop.services.customer_orders import ORDER_ACCESS_SESSION_KEY

        session = SessionStore()
        if order_refs:
            session[ORDER_ACCESS_SESSION_KEY] = list(order_refs)
        if superuser:
            User = get_user_model()
            user = (
                User._default_manager.filter(is_superuser=True, is_active=True)
                .order_by("pk")
                .first()
            )
            if user is None:
                user = User._default_manager.create_superuser(
                    username="storefront-e2e",
                    email="storefront-e2e@example.invalid",
                    password="unused-local-password",
                )
            session[SESSION_KEY] = str(user._meta.pk.value_to_string(user))
            session[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]
            session[HASH_SESSION_KEY] = user.get_session_auth_hash()
        session.save()
        return {"name": settings.SESSION_COOKIE_NAME, "value": session.session_key}


def _cookie_for(base_url: str, cookie: dict) -> dict:
    host = urlparse(base_url).hostname or "127.0.0.1"
    # Cookies ignore port, so a host-only cookie covers both the store (:3100)
    # and Django (:8001) origins on 127.0.0.1.
    return {
        "name": cookie["name"],
        "value": cookie["value"],
        "domain": host,
        "path": "/",
        "httpOnly": True,
        "sameSite": "Lax",
    }


@pytest.fixture
def grant_order_access(django_db_blocker, store_base_url):
    """Returns ``grant(context, *refs)`` — adds an order-access session cookie."""

    def grant(context, *refs):
        cookie = _in_thread(_mint_session, django_db_blocker, order_refs=refs)
        context.add_cookies([_cookie_for(store_base_url, cookie)])
        return cookie

    return grant


@pytest.fixture
def operator_session(django_db_blocker, operator_base_url):
    """Returns ``login(context)`` — binds a superuser session cookie."""

    def login(context):
        cookie = _in_thread(_mint_session, django_db_blocker, superuser=True)
        context.add_cookies([_cookie_for(operator_base_url, cookie)])
        return cookie

    return login
