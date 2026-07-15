"""Category 1 — IDOR sweep across every id/ref-bearing storefront endpoint.

Contract under test: a caller who is neither the owner nor a session-grantee of
a resource must get a **404** (never 403, never 200) — the same status as a
resource that does not exist, so there is no existence oracle to enumerate.

Covered:
- Every order-scoped endpoint (tracking, cancel, confirm-received, rate,
  confirmation, conversation, payment ×2, reorder, SSE events).
- Saved addresses (PATCH/DELETE/set-default) scoped to the owning customer.
- Both the anonymous attacker AND the logged-in-but-not-owner attacker.
- Uniform-404 assertion: non-owner status == nonexistent-ref status.
"""
from __future__ import annotations

import json

import pytest
from django.test import Client

from .conftest import login_as_customer

pytestmark = pytest.mark.django_db


# (method, url_template, body) for every endpoint that reads an order by ref.
# The victim order's ref is substituted for {ref}. The access gate
# (get_accessible_order / user_can_access_order) runs before any state/policy
# check, so a plain order fixture is enough to exercise the 404 path.
ORDER_ENDPOINTS = [
    ("get", "/api/v1/tracking/{ref}/", None),
    ("get", "/api/v1/tracking/{ref}/events/", None),  # SSE — stricter gate
    ("post", "/api/v1/orders/{ref}/cancel/", {}),
    ("post", "/api/v1/orders/{ref}/confirm-received/", {}),
    ("post", "/api/v1/orders/{ref}/rate/", {"rating": 5}),
    ("get", "/api/v1/orders/{ref}/confirmation/", None),
    ("get", "/api/v1/orders/{ref}/conversation/", None),
    ("get", "/api/v1/payment/{ref}/", None),
    ("get", "/api/v1/payment/{ref}/status/", None),
    ("post", "/api/v1/orders/{ref}/reorder/", {}),
]


def _call(client: Client, method: str, url: str, body):
    if method == "get":
        return client.get(url)
    return client.post(url, data=json.dumps(body or {}), content_type="application/json")


@pytest.mark.parametrize("method,template,body", ORDER_ENDPOINTS)
def test_anonymous_attacker_ref_guess_is_404(attacker, order, method, template, body):
    """An anonymous attacker guessing a valid order ref gets 404 on every
    order-scoped endpoint — no 200, no 403, no 500."""
    resp = _call(attacker, method, template.format(ref=order.ref), body)
    assert resp.status_code == 404, (
        f"{method.upper()} {template} leaked a non-404 to an anonymous non-owner: "
        f"{resp.status_code}"
    )


@pytest.mark.parametrize("method,template,body", ORDER_ENDPOINTS)
def test_logged_in_non_owner_is_404(attacker, other_customer, order, method, template, body):
    """A DIFFERENT authenticated customer (not the order's owner, different
    phone) still gets 404 on every order-scoped endpoint."""
    login_as_customer(attacker, other_customer)
    resp = _call(attacker, method, template.format(ref=order.ref), body)
    assert resp.status_code == 404, (
        f"{method.upper()} {template} leaked to a logged-in non-owner: {resp.status_code}"
    )


@pytest.mark.parametrize("method,template,body", ORDER_ENDPOINTS)
def test_non_owner_404_identical_to_nonexistent(attacker, order, method, template, body):
    """No existence oracle: the status for a real-but-foreign ref must equal the
    status for a ref that does not exist at all."""
    foreign = _call(attacker, method, template.format(ref=order.ref), body)
    missing = _call(attacker, method, template.format(ref="ORD-DOES-NOT-EXIST-XYZ"), body)
    assert foreign.status_code == missing.status_code == 404, (
        f"{method.upper()} {template}: foreign={foreign.status_code} "
        f"missing={missing.status_code} — enumeration oracle present"
    )


# ── Saved-address IDOR ────────────────────────────────────────────────────


def test_address_patch_foreign_pk_is_404(attacker, customer, victim_address):
    """A logged-in customer cannot PATCH another customer's address; the
    customer-scoped lookup returns 404 (not 403), same as a bogus pk."""
    login_as_customer(attacker, customer)
    foreign = attacker.patch(
        f"/api/v1/account/addresses/{victim_address.pk}/",
        data=json.dumps({"formatted_address": "Rua Invadida 1"}),
        content_type="application/json",
    )
    missing = attacker.patch(
        "/api/v1/account/addresses/99999999/",
        data=json.dumps({"formatted_address": "x"}),
        content_type="application/json",
    )
    assert foreign.status_code == missing.status_code == 404


def test_address_delete_foreign_pk_is_404_and_survives(attacker, customer, victim_address):
    """DELETE on a foreign address is 404 and does NOT delete the victim's row."""
    from shopman.guestman.models import CustomerAddress

    login_as_customer(attacker, customer)
    resp = attacker.delete(f"/api/v1/account/addresses/{victim_address.pk}/")
    assert resp.status_code == 404
    assert CustomerAddress.objects.filter(pk=victim_address.pk).exists(), (
        "IDOR: attacker deleted another customer's address"
    )


def test_address_set_default_foreign_pk_is_404(attacker, customer, victim_address):
    """POST ?action=default on a foreign address is 404, cannot flip the
    victim's default."""
    login_as_customer(attacker, customer)
    resp = attacker.post(f"/api/v1/account/addresses/{victim_address.pk}/?action=default")
    assert resp.status_code == 404


def test_address_endpoints_require_auth(attacker, victim_address):
    """Anonymous access to an address detail is 401 (auth boundary), never a
    500 or a silent 200."""
    resp = attacker.patch(
        f"/api/v1/account/addresses/{victim_address.pk}/",
        data=json.dumps({"formatted_address": "x"}),
        content_type="application/json",
    )
    assert resp.status_code == 401


# ── Owner still gets in (guard against over-blocking) ──────────────────────


def test_session_grantee_can_read_own_order(client, order):
    """The session that placed the order (grant in the `order` fixture) reads it
    with 200 — the 404 sweep above is not just blanket-denying everyone."""
    resp = client.get(f"/api/v1/tracking/{order.ref}/")
    assert resp.status_code == 200
    assert resp.json()["ref"] == order.ref


def test_address_owner_can_read_own(attacker, other_customer, victim_address):
    """The owning customer reads their own address list (positive control for
    the address IDOR tests)."""
    login_as_customer(attacker, other_customer)
    resp = attacker.get("/api/v1/account/addresses/")
    assert resp.status_code == 200
    ids = [a["id"] for a in resp.json()]
    assert victim_address.pk in ids
