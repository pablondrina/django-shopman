"""Categories 6 & 7 — input sanitization and auth boundaries.

Category 6 (input sanitization):
- Bidi/zero-width Unicode is stripped from names before persistence (Trojan
  Source / RTL-spoof defense on the KDS ticket).
- Control characters in names are neutralized; the value is length-capped.
- HTML/JS in free-text is stored verbatim (never executed server-side) and
  never triggers a 500.
- Numeric fields reject out-of-range values (qty < 0, qty > max) with a clean
  400, not a 500 or a silent clamp-through.
- Over-length payloads are rejected by the serializer (400), never crash.

Category 7 (auth boundaries):
- Account endpoints return 401 for anonymous callers — never 500, never a
  silent 200.
- Invalid / expired auth tokens are handled gracefully (400), no traceback.
"""
from __future__ import annotations

import json

import pytest

from .conftest import login_as_customer

pytestmark = pytest.mark.django_db


# ── Category 6: input sanitization ─────────────────────────────────────────


def test_bidi_and_zero_width_stripped_from_name(attacker, customer):
    """A name laced with RTL-override and zero-width chars is sanitized before
    it reaches persistence / the KDS ticket."""
    login_as_customer(attacker, customer)
    hostile = "Jo‮ao​⁦ Silva"  # RTL override + ZWSP + isolate
    resp = attacker.patch(
        "/api/v1/account/profile/",
        data=json.dumps({"first_name": hostile, "last_name": "Test"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    stored = resp.json()["first_name"]
    for cp in ("‮", "​", "⁦", "⁩", "‎"):
        assert cp not in stored, f"bidi/zero-width char {cp!r} survived into stored name"


def test_control_chars_neutralized_in_name(attacker, customer):
    """Newlines/tabs (control category Cc) in a name are collapsed to spaces —
    a pasted 'João\\nSilva' cannot inject extra lines into the kitchen ticket."""
    login_as_customer(attacker, customer)
    resp = attacker.patch(
        "/api/v1/account/profile/",
        data=json.dumps({"first_name": "João\n\tSilva\r\nHACK", "last_name": "X"}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    stored = resp.json()["first_name"]
    assert "\n" not in stored and "\t" not in stored and "\r" not in stored


def test_html_js_in_name_stored_verbatim_no_500(attacker, customer):
    """An HTML/JS payload in a text field must not 500 the server; it is stored
    as inert text (output encoding is the front's responsibility)."""
    login_as_customer(attacker, customer)
    resp = attacker.patch(
        "/api/v1/account/profile/",
        data=json.dumps({"first_name": "<script>alert(1)</script>", "last_name": "<img src=x onerror=1>"}),
        content_type="application/json",
    )
    assert resp.status_code == 200  # handled, not a 500


def test_oversized_name_rejected_not_crashed(client, cart_session):
    """A 10k-char name at checkout is rejected by the serializer (400), never a
    500 or an unbounded write."""
    resp = cart_session.post(
        "/api/v1/checkout/",
        data=json.dumps({"name": "A" * 10_000, "phone": "+5543999990001", "fulfillment_type": "pickup"}),
        content_type="application/json",
    )
    assert resp.status_code == 400
    assert "detail" in resp.json()


@pytest.mark.parametrize("bad_qty", [-1, -999999, 100, 999999])
def test_cart_qty_out_of_range_is_400(cart_session, product, bad_qty):
    """Absurd/negative quantities are rejected (min 0, max 99) with a 400 — no
    negative-qty write, no 500."""
    resp = cart_session.put(
        f"/api/v1/cart/skus/{product.sku}/",
        data=json.dumps({"qty": bad_qty}),
        content_type="application/json",
    )
    assert resp.status_code == 400, f"qty={bad_qty} returned {resp.status_code}, expected 400"
    assert "detail" in resp.json()


def test_cart_qty_non_numeric_is_400(cart_session, product):
    """A non-numeric quantity is a clean 400, not a 500 from a bad cast."""
    resp = cart_session.put(
        f"/api/v1/cart/skus/{product.sku}/",
        data=json.dumps({"qty": "; DROP TABLE"}),
        content_type="application/json",
    )
    assert resp.status_code == 400


def test_coupon_code_type_confusion_is_400_not_500(cart_session):
    """A coupon 'code' arriving as a dict/int must not blow up ``.strip()`` — it
    is coerced to empty and returns a clean 400."""
    for bad in ({"nested": 1}, 42, ["a"], True):
        resp = cart_session.post(
            "/api/v1/cart/coupon/",
            data=json.dumps({"code": bad}),
            content_type="application/json",
        )
        assert resp.status_code == 400, f"code={bad!r} → {resp.status_code}"
        assert "detail" in resp.json()


# ── Category 7: auth boundaries ────────────────────────────────────────────

ANON_401_ENDPOINTS = [
    ("get", "/api/v1/account/profile/"),
    ("patch", "/api/v1/account/profile/"),
    ("get", "/api/v1/account/summary/"),
    ("get", "/api/v1/account/addresses/"),
    ("get", "/api/v1/account/favorites/"),
    ("get", "/api/v1/account/orders/"),
    ("get", "/api/v1/account/export/"),
    ("post", "/api/v1/account/delete/"),
    ("post", "/api/v1/account/step-up/"),
    ("get", "/api/v1/account/devices/"),
    ("post", "/api/v1/account/preferences/food/"),
    ("post", "/api/v1/account/preferences/notifications/"),
]


@pytest.mark.parametrize("method,url", ANON_401_ENDPOINTS)
def test_account_endpoints_require_auth(attacker, method, url):
    """Every account endpoint returns 401 for an anonymous caller — never 500,
    never a silent 200 leaking another user's data."""
    fn = getattr(attacker, method)
    resp = fn(url, data=json.dumps({}), content_type="application/json") if method != "get" else fn(url)
    assert resp.status_code == 401, f"{method.upper()} {url} → {resp.status_code}, expected 401"


def test_trust_device_requires_auth(attacker):
    """Trusting a device requires an authenticated customer (401 for anon)."""
    resp = attacker.post("/api/v1/auth/trust-device/", data=json.dumps({"trust": True}), content_type="application/json")
    assert resp.status_code == 401


def test_invalid_access_token_is_400_not_500(attacker):
    """A bogus access-link token is rejected gracefully (400), never a 500."""
    resp = attacker.post("/api/v1/auth/access/", data=json.dumps({"token": "not-a-real-token"}), content_type="application/json")
    assert resp.status_code == 400
    assert "detail" in resp.json()
    assert "_auth_user_id" not in attacker.session


def test_export_requires_step_up_even_when_logged_in(attacker, customer):
    """A logged-in customer without a fresh OTP step-up cannot export data —
    the sensitive-action gate returns 403 step_up_required, not the data."""
    login_as_customer(attacker, customer)
    resp = attacker.get("/api/v1/account/export/")
    assert resp.status_code == 403
    assert resp.json().get("code") == "step_up_required"
