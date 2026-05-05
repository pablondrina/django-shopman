"""
DB-level integration tests for WP-DF-3 — Hold adoption by quantity.

Unlike `test_hold_adoption.py`, these tests use REAL Hold/Quant rows and
the REAL stock adapter (no mocks). They verify the end-to-end effect of:

  - services.stock.hold(order) FIFO adoption summing quantity
  - services.stock._retag_hold_for_order metadata mutation
  - services.stock leftover release for unconsumed session holds
  - services.availability.reconcile() grow / shrink (with overshoot
    compensation) / zero / no-op
  - Full cart lifecycle: reserve × N → reconcile (grow/shrink) → commit
    adoption → final reserved qty matches the final cart qty.

These exercise the actual SQL side effects, closing the trust gap left by
the mock-heavy unit tests.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from shopman.offerman.models import Product
from shopman.stockman import HoldStatus, PositionKind, StockHolds
from shopman.stockman.models import Hold, Position, Quant

from shopman.shop.adapters import get_adapter
from shopman.shop.models import Channel
from shopman.shop.services import availability
from shopman.shop.services import stock as stock_service

SKU = "WP-DF3-INT"
SESSION_KEY = "sess-int-1"
ORDER_REF = "ORD-INT-1"
CHANNEL_REF = "web"


# ── Fixtures ──────────────────────────────────────────────────────────────


def _setup_world(stock_qty: int = 100) -> Product:
    """Create the minimum DB state for a real cart→hold→adopt cycle."""
    Channel.objects.create(
        ref=CHANNEL_REF,
        name="Web",
        is_active=True,
    )
    product = Product.objects.create(
        sku=SKU,
        name="Test Product",
        base_price_q=1000,
        is_published=True,
        is_sellable=True,
    )
    pos, _ = Position.objects.get_or_create(
        ref="vitrine",
        defaults={
            "name": "Vitrine",
            "kind": PositionKind.PHYSICAL,
            "is_saleable": True,
        },
    )
    Quant.objects.create(sku=SKU, position=pos, _quantity=Decimal(str(stock_qty)))
    return product


def _make_session_hold(qty: int) -> str:
    """Create a real Hold tagged with SESSION_KEY via the framework adapter."""
    adapter = get_adapter("stock")
    result = adapter.create_hold(
        sku=SKU,
        qty=Decimal(str(qty)),
        reference=SESSION_KEY,
        cart_source_sku=SKU,
    )
    assert result["success"], result
    return result["hold_id"]


def _make_order(items_qty: int) -> SimpleNamespace:
    """Build a fake order object with the bare attrs services.stock.hold needs."""
    return SimpleNamespace(
        ref=ORDER_REF,
        session_key=SESSION_KEY,
        snapshot={"items": [{"sku": SKU, "qty": items_qty}]},
        data={},
        save=lambda update_fields=None: None,
    )


def _hold_pk(hold_id: str) -> int:
    return int(hold_id.split(":")[1])


def _active_session_holds() -> list[Hold]:
    return list(
        StockHolds.find_by_reference(
            SESSION_KEY,
            status_in=[HoldStatus.PENDING],
        )
    )


def _order_holds() -> list[Hold]:
    return list(
        StockHolds.find_by_reference(
            f"order:{ORDER_REF}",
            status_in=[HoldStatus.PENDING],
        )
    )


# ── services.stock.hold() — adoption FIFO + sum + leftover release ────────


@pytest.mark.django_db
class TestHoldAdoptionDB:
    def test_two_session_holds_cover_order_line_summed(self):
        """Holds [2, 3] cover an order line of qty=5 — both adopted, no fresh."""
        _setup_world()
        h1 = _make_session_hold(2)
        h2 = _make_session_hold(3)

        stock_service.hold(_make_order(5))

        h1_row = Hold.objects.get(pk=_hold_pk(h1))
        h2_row = Hold.objects.get(pk=_hold_pk(h2))
        assert h1_row.metadata["reference"] == f"order:{ORDER_REF}"
        assert h2_row.metadata["reference"] == f"order:{ORDER_REF}"

        order_holds = _order_holds()
        assert len(order_holds) == 2
        assert sum(h.quantity for h in order_holds) == Decimal("5")
        # Nothing leaked: no session-tagged holds remain.
        assert _active_session_holds() == []

    def test_partial_session_creates_fresh_hold_for_remainder(self):
        """Session has qty=2 but order needs qty=5 → fresh hold for qty=3."""
        _setup_world()
        h1 = _make_session_hold(2)

        stock_service.hold(_make_order(5))

        order_holds = _order_holds()
        assert len(order_holds) == 2
        # Order is FIFO by pk: adopted first, then fresh.
        assert order_holds[0].pk == _hold_pk(h1)
        assert order_holds[0].quantity == Decimal("2")
        assert order_holds[1].quantity == Decimal("3")
        assert sum(h.quantity for h in order_holds) == Decimal("5")

    def test_overshoot_session_hold_is_accepted(self):
        """Session has qty=5 but order needs qty=2 — adopt the whole hold."""
        _setup_world()
        h1 = _make_session_hold(5)

        stock_service.hold(_make_order(2))

        order_holds = _order_holds()
        assert len(order_holds) == 1
        # Whole hold consumed even though it overshoots — splitting would
        # require a new Stockman API and the residual reservation is benign.
        assert order_holds[0].pk == _hold_pk(h1)
        assert order_holds[0].quantity == Decimal("5")

    def test_leftover_session_holds_released_when_order_smaller(self):
        """Session has [2, 3] but order only needs qty=2 → adopt h1, release h2."""
        _setup_world()
        h1 = _make_session_hold(2)
        h2 = _make_session_hold(3)

        stock_service.hold(_make_order(2))

        h1_row = Hold.objects.get(pk=_hold_pk(h1))
        h2_row = Hold.objects.get(pk=_hold_pk(h2))
        assert h1_row.metadata["reference"] == f"order:{ORDER_REF}"
        assert h1_row.status == HoldStatus.PENDING
        assert h2_row.status == HoldStatus.RELEASED

    def test_no_session_holds_creates_full_fresh_hold(self):
        """No session reservations at all → entire qty comes from a fresh hold."""
        _setup_world()

        stock_service.hold(_make_order(4))

        order_holds = _order_holds()
        assert len(order_holds) == 1
        assert order_holds[0].quantity == Decimal("4")


# ── services.availability.reconcile() — grow / shrink / zero / no-op ──────


@pytest.mark.django_db
class TestReconcileDB:
    def test_noop_when_qty_unchanged(self):
        _setup_world()
        h1 = _make_session_hold(5)

        result = availability.reconcile(
            sku=SKU,
            new_qty=Decimal("5"),
            session_key=SESSION_KEY,
            channel_ref=CHANNEL_REF,
        )

        assert result["ok"]
        assert result["hold_ids"] == []
        assert result["released_ids"] == []
        # Original hold is untouched.
        h1_row = Hold.objects.get(pk=_hold_pk(h1))
        assert h1_row.status == HoldStatus.PENDING
        assert h1_row.quantity == Decimal("5")

    def test_grow_creates_delta_hold(self):
        _setup_world()
        h1 = _make_session_hold(2)

        result = availability.reconcile(
            sku=SKU,
            new_qty=Decimal("5"),
            session_key=SESSION_KEY,
            channel_ref=CHANNEL_REF,
        )

        assert result["ok"]
        active = _active_session_holds()
        assert len(active) == 2
        assert active[0].pk == _hold_pk(h1)
        assert active[0].quantity == Decimal("2")
        assert active[1].quantity == Decimal("3")  # delta
        assert sum(h.quantity for h in active) == Decimal("5")

    def test_grow_returns_shortage_without_touching_existing_holds(self):
        """When stock can't cover the delta, existing holds must remain intact."""
        _setup_world(stock_qty=4)  # only 4 in stock
        h1 = _make_session_hold(2)  # consumes 2 from the 4

        result = availability.reconcile(
            sku=SKU,
            new_qty=Decimal("10"),  # delta = 8, but only 2 available
            session_key=SESSION_KEY,
            channel_ref=CHANNEL_REF,
        )

        assert not result["ok"]
        assert result["error_code"] in ("insufficient_supply", "no_listing")
        # Existing hold preserved.
        h1_row = Hold.objects.get(pk=_hold_pk(h1))
        assert h1_row.status == HoldStatus.PENDING
        assert h1_row.quantity == Decimal("2")
        # No new holds created.
        assert len(_active_session_holds()) == 1

    def test_shrink_releases_fifo_with_compensating_hold(self):
        """Holds [2, 3], shrink to qty=2 → release both, create comp qty=2."""
        _setup_world()
        h1 = _make_session_hold(2)
        h2 = _make_session_hold(3)

        result = availability.reconcile(
            sku=SKU,
            new_qty=Decimal("2"),
            session_key=SESSION_KEY,
            channel_ref=CHANNEL_REF,
        )

        # Math: current=5, target=2, diff=3.
        # FIFO: release h1 (qty=2), released=2 < 3, release h2 (qty=3),
        # released=5 ≥ 3, stop. Overshoot = 5 - 3 = 2 → compensating qty=2.
        assert result["ok"]
        assert Hold.objects.get(pk=_hold_pk(h1)).status == HoldStatus.RELEASED
        assert Hold.objects.get(pk=_hold_pk(h2)).status == HoldStatus.RELEASED

        active = _active_session_holds()
        assert len(active) == 1
        assert active[0].quantity == Decimal("2")
        assert active[0].pk not in (_hold_pk(h1), _hold_pk(h2))  # truly new

    def test_shrink_exact_match_no_compensating_hold(self):
        """Holds [2, 3], shrink to qty=3 → release h1 only, h2 untouched."""
        _setup_world()
        h1 = _make_session_hold(2)
        h2 = _make_session_hold(3)

        result = availability.reconcile(
            sku=SKU,
            new_qty=Decimal("3"),
            session_key=SESSION_KEY,
            channel_ref=CHANNEL_REF,
        )

        # diff = 5 - 3 = 2; release h1 (qty=2), released=2 == diff, stop.
        # No overshoot → no compensating hold.
        assert result["ok"]
        assert result["hold_ids"] == []  # nothing newly created
        assert Hold.objects.get(pk=_hold_pk(h1)).status == HoldStatus.RELEASED
        assert Hold.objects.get(pk=_hold_pk(h2)).status == HoldStatus.PENDING

        active = _active_session_holds()
        assert len(active) == 1
        assert active[0].pk == _hold_pk(h2)  # original untouched
        assert active[0].quantity == Decimal("3")

    def test_zero_releases_everything(self):
        _setup_world()
        h1 = _make_session_hold(2)
        h2 = _make_session_hold(3)

        result = availability.reconcile(
            sku=SKU,
            new_qty=Decimal("0"),
            session_key=SESSION_KEY,
            channel_ref=CHANNEL_REF,
        )

        assert result["ok"]
        assert Hold.objects.get(pk=_hold_pk(h1)).status == HoldStatus.RELEASED
        assert Hold.objects.get(pk=_hold_pk(h2)).status == HoldStatus.RELEASED
        assert _active_session_holds() == []


# ── End-to-end: full cart → reconcile → commit lifecycle ──────────────────


@pytest.mark.django_db
class TestCartLifecycleDB:
    def test_reserve_grow_shrink_commit_yields_exact_final_qty(self):
        """add 2 → add 3 → grow to 10 → shrink to 4 → commit adopts == 4."""
        _setup_world(stock_qty=100)

        # Two reserves (the cart's add_item path).
        r1 = availability.reserve(
            SKU, Decimal("2"),
            session_key=SESSION_KEY, channel_ref=CHANNEL_REF,
        )
        assert r1["ok"]
        r2 = availability.reserve(
            SKU, Decimal("3"),
            session_key=SESSION_KEY, channel_ref=CHANNEL_REF,
        )
        assert r2["ok"]

        # After both reserves: 2 holds totalling 5.
        assert sum(h.quantity for h in _active_session_holds()) == Decimal("5")

        # Stepper grows to 10.
        availability.reconcile(
            sku=SKU, new_qty=Decimal("10"),
            session_key=SESSION_KEY, channel_ref=CHANNEL_REF,
        )
        assert sum(h.quantity for h in _active_session_holds()) == Decimal("10")

        # Stepper shrinks to 4.
        availability.reconcile(
            sku=SKU, new_qty=Decimal("4"),
            session_key=SESSION_KEY, channel_ref=CHANNEL_REF,
        )
        assert sum(h.quantity for h in _active_session_holds()) == Decimal("4")

        # Commit: adopt all session holds onto the order.
        stock_service.hold(_make_order(4))

        order_holds = _order_holds()
        assert sum(h.quantity for h in order_holds) == Decimal("4")
        # No session leftovers — everything moved to the order.
        assert _active_session_holds() == []
