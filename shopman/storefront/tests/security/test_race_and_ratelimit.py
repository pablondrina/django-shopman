"""Categories 4 & 5 — race conditions and rate limiting.

Category 4 (races):
- Checkout idempotency: the same idempotency key never creates two orders.
- Coupon ``max_uses`` guard: a single-use coupon redeemed twice caps at one use
  AND the second order receives no discount (sequential gate). A PostgreSQL-only
  test documents the true-concurrency TOCTOU window.
- Stock holds are atomic: two carts cannot each hold the last unit (no oversell
  at add-to-cart).

Category 5 (rate limiting):
- Sensitive endpoints (OTP request/verify, checkout) are rate-limited.
- The limit keys off the real client IP (rightmost X-Forwarded-For via
  ``client_ip``), not the shared proxy REMOTE_ADDR, so one abuser cannot lock
  out the whole store. (The broad matrix lives in ``tests/test_rate_limiting``;
  here we assert the security-relevant isolation and a spoofing caveat.)
"""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client, override_settings
from django.utils import timezone
from shopman.offerman.models import Product
from shopman.orderman.models import Order

from shopman.shop.services import checkout as checkout_service
from shopman.shop.services import sessions as session_service

pytestmark = pytest.mark.django_db

requires_postgres = pytest.mark.skipif(
    "sqlite" in settings.DATABASES["default"]["ENGINE"],
    reason="Requires PostgreSQL for real concurrency (row-level locking).",
)


def _seed_stock(sku: str, qty: int) -> None:
    from shopman.stockman import stock
    from shopman.stockman.models import Position, PositionKind

    pos, _ = Position.objects.get_or_create(
        ref="loja",
        defaults={"name": "Loja Principal", "kind": PositionKind.PHYSICAL, "is_saleable": True},
    )
    stock.receive(Decimal(str(qty)), sku, pos, target_date=timezone.localdate(), reason="security seed")


def _open_session_with_item(sku: str, name: str, qty: int, price_q: int):
    session = session_service.create_session("web")
    session_service.modify_session(
        session_key=session.session_key,
        channel_ref="web",
        ops=[
            {"op": "add_line", "sku": sku, "name": name, "qty": qty, "unit_price_q": price_q},
            {"op": "set_data", "path": "customer", "value": {"name": "Ana", "phone": "+5543999990001"}},
            {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        ],
    )
    return session


# ── Category 4: idempotency ────────────────────────────────────────────────


def test_double_submit_never_duplicates_order(channel, product):
    """A committed session cannot be committed again: a replayed checkout either
    returns the same order or is rejected, but NEVER creates a second order
    (double-submit / retry safety)."""
    session = _open_session_with_item(product.sku, product.name, 1, 500)
    key = session_service.new_idempotency_key()
    data = {"customer": {"name": "Ana", "phone": "+5543999990001"}, "fulfillment_type": "pickup"}

    r1 = checkout_service.process(session_key=session.session_key, channel_ref="web", data=data, idempotency_key=key)
    try:
        r2 = checkout_service.process(session_key=session.session_key, channel_ref="web", data=data, idempotency_key=key)
        assert r2.order_ref == r1.order_ref  # cached replay is fine
    except Exception:
        pass  # rejecting the second submit is also acceptable — the guarantee is no dup

    assert Order.objects.filter(session_key=session.session_key).count() == 1


def test_commit_idempotency_key_returns_cached_order(channel, product):
    """At the commit boundary, the same idempotency key on a fresh + already
    committed session returns the SAME order (never a second)."""
    from shopman.orderman.services.commit import CommitService

    session = _open_session_with_item(product.sku, product.name, 1, 500)
    key = "IDEM-SEC-001"
    r1 = CommitService.commit(session_key=session.session_key, channel_ref="web", idempotency_key=key)
    r2 = CommitService.commit(session_key=session.session_key, channel_ref="web", idempotency_key=key)
    assert r1.order_ref == r2.order_ref
    assert Order.objects.filter(session_key=session.session_key).count() == 1


# ── Category 4: coupon max_uses guard ──────────────────────────────────────


def _coupon(code: str, *, max_uses: int, value: int = 500):
    from shopman.storefront.models import Coupon, Promotion

    now = timezone.now()
    promo = Promotion.objects.create(
        name=f"Promo {code}",
        type=Promotion.FIXED,
        value=value,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=1),
    )
    return Coupon.objects.create(code=code, promotion=promo, max_uses=max_uses)


def test_single_use_coupon_second_order_gets_no_discount(channel, django_capture_on_commit_callbacks):
    """A ``max_uses=1`` coupon: the first order redeems it and the SECOND order
    (sequential) receives no discount — the availability gate at commit denies
    re-application, and uses_count never exceeds 1."""
    Product.objects.create(sku="PAO-CUP", name="Pão", base_price_q=2500, is_published=True, is_sellable=True)
    coupon = _coupon("UNICO", max_uses=1, value=500)

    def _commit(session_key_suffix: str) -> Order:
        session = session_service.create_session("web")
        session_service.modify_session(
            session_key=session.session_key,
            channel_ref="web",
            ops=[
                {"op": "add_line", "sku": "PAO-CUP", "name": "Pão", "qty": 1, "unit_price_q": 2500},
                {"op": "set_data", "path": "customer", "value": {"name": "Ana", "phone": "+5543999990001"}},
                {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
                {"op": "set_data", "path": "coupon_code", "value": "UNICO"},
            ],
        )
        with django_capture_on_commit_callbacks(execute=True):
            res = checkout_service.process(
                session_key=session.session_key,
                channel_ref="web",
                data={"customer": {"name": "Ana", "phone": "+5543999990001"}, "fulfillment_type": "pickup"},
                idempotency_key=session_service.new_idempotency_key(),
            )
        return Order.objects.get(ref=res.order_ref)

    first = _commit("a")
    second = _commit("b")

    coupon.refresh_from_db()
    assert coupon.uses_count == 1, f"uses_count over the cap: {coupon.uses_count}"
    # First order got R$5,00 off (2500 → 2000); second pays full price.
    assert first.total_q == 2000
    assert second.total_q == 2500, (
        f"single-use coupon re-applied on 2nd order: total {second.total_q}, expected 2500"
    )


@requires_postgres
def test_single_use_coupon_no_concurrent_over_redemption(channel):
    """TRUE-concurrency guard (PostgreSQL): two threads committing the same
    single-use coupon simultaneously must not both receive the discount, and
    uses_count must not exceed 1. Documents the commit-modifier vs
    record_coupon_use TOCTOU window."""
    import threading

    Product.objects.create(sku="PAO-RACE", name="Pão", base_price_q=2500, is_published=True, is_sellable=True)
    coupon = _coupon("RACE1", max_uses=1, value=500)
    results: list[int] = []
    lock = threading.Lock()

    def _worker(idx: int):
        session = session_service.create_session("web")
        session_service.modify_session(
            session_key=session.session_key,
            channel_ref="web",
            ops=[
                {"op": "add_line", "sku": "PAO-RACE", "name": "Pão", "qty": 1, "unit_price_q": 2500},
                {"op": "set_data", "path": "customer", "value": {"name": "Ana", "phone": "+5543999990001"}},
                {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
                {"op": "set_data", "path": "coupon_code", "value": "RACE1"},
            ],
        )
        res = checkout_service.process(
            session_key=session.session_key,
            channel_ref="web",
            data={"customer": {"name": "Ana", "phone": "+5543999990001"}, "fulfillment_type": "pickup"},
            idempotency_key=session_service.new_idempotency_key(),
        )
        order = Order.objects.get(ref=res.order_ref)
        with lock:
            results.append(order.total_q)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    coupon.refresh_from_db()
    assert coupon.uses_count <= 1
    discounted = [t for t in results if t == 2000]
    assert len(discounted) <= 1, f"coupon discount granted to {len(discounted)} orders (over-redemption)"


# ── Category 4: stock hold atomicity (oversell) ────────────────────────────


def test_last_unit_cannot_be_held_by_two_carts(channel):
    """Stock = 1. Cart A reserves the unit at add-to-cart; Cart B's add for the
    same SKU is refused (no oversell of the last unit, sequential)."""
    from shopman.shop.services import cart as cart_svc
    from shopman.shop.services.cart import CartUnavailableError

    Product.objects.create(sku="LAST-ONE", name="Último", base_price_q=1000, is_published=True, is_sellable=True)
    from shopman.offerman.models import Listing, ListingItem
    listing, _ = Listing.objects.get_or_create(ref="web", defaults={"name": "web", "is_active": True, "priority": 10})
    ListingItem.objects.get_or_create(
        listing=listing, product=Product.objects.get(sku="LAST-ONE"),
        defaults={"price_q": 1000, "is_published": True, "is_sellable": True},
    )
    _seed_stock("LAST-ONE", 1)

    # Cart A grabs the only unit.
    cart_svc.add_item(
        session_key=None, channel_ref="web", origin_channel="web",
        sku="LAST-ONE", qty=1, unit_price_q=1000, name="Último",
    )
    # Cart B (independent session) is refused.
    with pytest.raises(CartUnavailableError):
        cart_svc.add_item(
            session_key=None, channel_ref="web", origin_channel="web",
            sku="LAST-ONE", qty=1, unit_price_q=1000, name="Último",
        )


# ── Category 5: rate limiting ──────────────────────────────────────────────


@pytest.fixture
def _stub_window():
    """Freeze django-ratelimit's window so counters accumulate within the test."""
    from unittest.mock import patch

    cache.clear()
    with patch("django_ratelimit.core._get_window", return_value=2_000_000_000):
        yield
    cache.clear()


@override_settings(RATELIMIT_ENABLE=True)
def test_otp_request_is_rate_limited(_stub_window):
    """The 6th OTP request in the window is throttled (brute-force / SMS-bomb
    defense) — 5/min per client IP."""
    client = Client()
    body = json.dumps({"phone": "+5511999990001"})
    for _ in range(5):
        assert client.post("/api/v1/auth/request-code/", data=body, content_type="application/json").status_code != 429
    assert client.post("/api/v1/auth/request-code/", data=body, content_type="application/json").status_code == 429


@override_settings(RATELIMIT_ENABLE=True)
def test_otp_limit_isolates_clients_by_real_ip_not_shared_proxy(_stub_window):
    """Behind a load balancer every request shares one REMOTE_ADDR; the limit
    must key off the real client IP (rightmost XFF) so an aggressive client
    cannot exhaust the store-wide OTP budget for everyone else."""
    proxy = "10.0.0.1"

    def _req(xff: str):
        # TRUSTED_PROXY_DEPTH=1 → client_ip uses the rightmost XFF entry, which
        # the trusted LB sets to the real client IP (single value here).
        return Client().post(
            "/api/v1/auth/request-code/",
            data=json.dumps({"phone": "+5511999990010"}),
            content_type="application/json",
            REMOTE_ADDR=proxy,
            HTTP_X_FORWARDED_FOR=xff,
        )

    for _ in range(5):
        assert _req("9.9.9.9").status_code != 429
    assert _req("9.9.9.9").status_code == 429       # abuser blocked
    assert _req("8.8.8.8").status_code != 429        # bystander unaffected


@override_settings(RATELIMIT_ENABLE=True)
def test_spoofed_single_value_xff_controls_rate_limit_key(_stub_window):
    """SECURITY CAVEAT (documented, not a failure): with TRUSTED_PROXY_DEPTH=1,
    ``client_ip`` returns the RIGHTMOST XFF entry. A direct-connecting attacker
    who sends a single-value ``X-Forwarded-For`` fully controls the rate-limit
    key and can rotate it to bypass the per-IP OTP limit. This is safe ONLY if a
    trusted proxy always appends the real client IP. Assert the rotation-bypass
    to make the trusted-proxy assumption explicit and testable."""
    def _req(spoof: str):
        return Client().post(
            "/api/v1/auth/request-code/",
            data=json.dumps({"phone": "+5511999990020"}),
            content_type="application/json",
            REMOTE_ADDR="203.0.113.7",
            HTTP_X_FORWARDED_FOR=spoof,  # single value → parts[-1] is attacker-controlled
        )

    for _ in range(5):
        assert _req("1.1.1.1").status_code != 429
    assert _req("1.1.1.1").status_code == 429        # key "1.1.1.1" exhausted
    # Rotating the forged single-value XFF yields a fresh bucket → bypass.
    assert _req("2.2.2.2").status_code != 429
