"""
WP-DF-3 — Tests for hold adoption by quantity.

Scenarios from DRIFT-FIX-PLAN.md:

- add X twice → commit adopts two holds totaling qty=4
- add then update up → reserve total=5
- add then update down → reserve total=2 (FIFO release + compensating hold)
- add then remove → zero holds
- reconcile shortage → error, no mutation
- leftover release → Hold Y released on remove, not on commit leftover sweep

These tests use mocks for the adapter and `_load_session_holds_for_sku` so
they exercise the pure orchestration logic without a seeded Stockman.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from shopman.shop.models import Channel

# ── helpers ──


def _ok_status(available=100):
    return {
        "ok": True,
        "available_qty": Decimal(str(available)),
        "is_paused": False,
        "is_planned": False,
        "breakdown": {},
        "error_code": None,
        "is_bundle": False,
        "failed_sku": None,
    }


def _shortage_status(available=0):
    return {
        "ok": False,
        "available_qty": Decimal(str(available)),
        "is_paused": False,
        "is_planned": False,
        "breakdown": {},
        "error_code": "insufficient_stock",
        "is_bundle": False,
        "failed_sku": None,
    }


def _make_order(ref="ORD-001", items=None, session_key="sess-1"):
    order = MagicMock()
    order.ref = ref
    order.session_key = session_key
    order.data = {}
    order.snapshot = {"items": items or [], "data": {}}
    return order


# ══════════════════════════════════════════════════════════════════════
# services.stock.hold — adoption by quantity at commit time
# ══════════════════════════════════════════════════════════════════════


class TestHoldAdoptionByQuantity:
    """Commit-time adoption consumes session holds until required qty is met."""

    @patch("shopman.shop.services.stock._retag_hold_for_order")
    @patch("shopman.shop.services.stock._load_session_holds")
    @patch("shopman.shop.services.stock.get_adapter")
    def test_add_twice_adopts_both_holds(
        self, mock_get_adapter, mock_load, mock_retag,
    ):
        """add(X, 2) + add(X, 2) → commit → two holds adopted, total qty=4."""
        from shopman.shop.services.stock import hold

        adapter = MagicMock()
        adapter.expand_bundle.side_effect = Exception("NOT_A_BUNDLE")
        mock_get_adapter.return_value = adapter
        mock_load.return_value = {
            "X": [
                ("hold:A", Decimal("2")),
                ("hold:B", Decimal("2")),
            ],
        }

        order = _make_order(items=[{"sku": "X", "qty": "4"}])
        hold(order)

        adapter.create_hold.assert_not_called()
        adapter.release_holds.assert_not_called()
        entries = order.data["hold_ids"]
        assert {e["hold_id"] for e in entries} == {"hold:A", "hold:B"}
        assert sum(Decimal(str(e["qty"])) for e in entries) == Decimal("4")

    @patch("shopman.shop.services.stock._retag_hold_for_order")
    @patch("shopman.shop.services.stock._load_session_holds")
    @patch("shopman.shop.services.stock.get_adapter")
    def test_partial_session_holds_fills_remainder_with_fresh_hold(
        self, mock_get_adapter, mock_load, mock_retag,
    ):
        """Session covers qty=2 of required=5 → adopt 2, create fresh 3."""
        from shopman.shop.services.stock import hold

        adapter = MagicMock()
        adapter.expand_bundle.side_effect = Exception("NOT_A_BUNDLE")
        adapter.create_hold.return_value = {"success": True, "hold_id": "hold:FRESH"}
        mock_get_adapter.return_value = adapter
        mock_load.return_value = {
            "X": [("hold:A", Decimal("2"))],
        }

        order = _make_order(items=[{"sku": "X", "qty": "5"}])
        hold(order)

        adapter.create_hold.assert_called_once()
        assert adapter.create_hold.call_args.kwargs["qty"] == Decimal("3")

        entries = order.data["hold_ids"]
        assert {e["hold_id"] for e in entries} == {"hold:A", "hold:FRESH"}

    @patch("shopman.shop.services.stock._retag_hold_for_order")
    @patch("shopman.shop.services.stock._load_session_holds")
    @patch("shopman.shop.services.stock.get_adapter")
    def test_overshoot_hold_released_and_fresh_hold_created(
        self, mock_get_adapter, mock_load, mock_retag,
    ):
        """Overshoot hold is released immediately; fresh hold covers exact remainder."""
        from shopman.shop.services.stock import hold

        adapter = MagicMock()
        adapter.expand_bundle.side_effect = Exception("NOT_A_BUNDLE")
        adapter.create_hold.return_value = {"success": True, "hold_id": "hold:FRESH"}
        mock_get_adapter.return_value = adapter
        mock_load.return_value = {
            "X": [
                ("hold:A", Decimal("2")),
                ("hold:B", Decimal("3")),  # would overshoot: 2+3=5 > required=4
            ],
        }

        order = _make_order(items=[{"sku": "X", "qty": "4"}])
        hold(order)

        # hold:B released immediately; fresh hold for the remaining 2 created.
        adapter.release_holds.assert_called_once_with(["hold:B"])
        adapter.create_hold.assert_called_once()
        assert adapter.create_hold.call_args.kwargs["qty"] == Decimal("2")

        entries = order.data["hold_ids"]
        assert {e["hold_id"] for e in entries} == {"hold:A", "hold:FRESH"}
        assert sum(Decimal(str(e["qty"])) for e in entries) == Decimal("4")

    @patch("shopman.shop.services.stock._retag_hold_for_order")
    @patch("shopman.shop.services.stock._load_session_holds")
    @patch("shopman.shop.services.stock.get_adapter")
    def test_leftover_holds_released(
        self, mock_get_adapter, mock_load, mock_retag,
    ):
        """Session hold for SKU not in order → released at commit (safety net)."""
        from shopman.shop.services.stock import hold

        adapter = MagicMock()
        adapter.expand_bundle.side_effect = Exception("NOT_A_BUNDLE")
        mock_get_adapter.return_value = adapter
        mock_load.return_value = {
            "X": [("hold:X1", Decimal("2"))],
            "Y": [("hold:Y1", Decimal("1"))],  # leftover — Y not in order
        }

        order = _make_order(items=[{"sku": "X", "qty": "2"}])
        hold(order)

        adapter.release_holds.assert_called_once_with(["hold:Y1"])


# ══════════════════════════════════════════════════════════════════════
# services.availability.reconcile — mid-cart hold adjustment
# ══════════════════════════════════════════════════════════════════════


class TestReconcileSimple:
    """reconcile() for non-bundle SKUs covers add → update up/down → remove."""

    @patch("shopman.shop.services.availability._load_session_holds_for_sku")
    @patch("shopman.shop.services.availability.get_adapter")
    @patch("shopman.shop.services.availability.check")
    def test_reconcile_noop_when_already_at_target(
        self, mock_check, mock_get_adapter, mock_load_sku,
    ):
        from shopman.shop.services.availability import reconcile

        mock_load_sku.return_value = [("hold:A", Decimal("3"))]
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter

        result = reconcile("X", Decimal("3"), session_key="s1", channel_ref="web")

        assert result["ok"] is True
        adapter.create_hold.assert_not_called()
        adapter.release_holds.assert_not_called()

    @patch("shopman.shop.services.availability._expand_if_bundle", return_value=None)
    @patch("shopman.shop.services.availability.substitutes")
    @patch("shopman.shop.services.availability._load_session_holds_for_sku")
    @patch("shopman.shop.services.availability.get_adapter")
    @patch("shopman.shop.services.availability.check")
    def test_reconcile_grow_creates_delta_hold(
        self, mock_check, mock_get_adapter, mock_load_sku, mock_alts, mock_expand,
    ):
        """update_qty from 2 → 5 creates a fresh hold for the delta=3."""
        from shopman.shop.services.availability import reconcile

        mock_load_sku.return_value = [("hold:A", Decimal("2"))]
        mock_check.return_value = _ok_status(available=100)
        adapter = MagicMock()
        adapter.create_hold.return_value = {
            "success": True, "hold_id": "hold:GROW",
        }
        mock_get_adapter.return_value = adapter

        result = reconcile("X", Decimal("5"), session_key="s1", channel_ref="web")

        assert result["ok"] is True
        adapter.release_holds.assert_not_called()
        adapter.create_hold.assert_called_once()
        kwargs = adapter.create_hold.call_args.kwargs
        assert kwargs["sku"] == "X"
        assert kwargs["qty"] == Decimal("3")
        assert kwargs["reference"] == "s1"
        assert result["hold_ids"] == ["hold:GROW"]

    @patch("shopman.shop.services.availability._expand_if_bundle", return_value=None)
    @patch("shopman.shop.services.availability.substitutes")
    @patch("shopman.shop.services.availability._load_session_holds_for_sku")
    @patch("shopman.shop.services.availability.get_adapter")
    @patch("shopman.shop.services.availability.check")
    def test_reconcile_grow_shortage_returns_error(
        self, mock_check, mock_get_adapter, mock_load_sku, mock_alts, mock_expand,
    ):
        """Insufficient stock on grow → ok=False, no mutation, substitutes set."""
        from shopman.shop.services.availability import reconcile

        mock_load_sku.return_value = [("hold:A", Decimal("5"))]
        mock_check.return_value = _shortage_status(available=3)
        mock_alts.find.return_value = [{"sku": "ALT-1"}]
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter

        result = reconcile("X", Decimal("999"), session_key="s1", channel_ref="web")

        assert result["ok"] is False
        assert result["error_code"] == "insufficient_stock"
        assert result["substitutes"] == [{"sku": "ALT-1"}]
        adapter.create_hold.assert_not_called()
        adapter.release_holds.assert_not_called()

    @patch("shopman.shop.services.availability._expand_if_bundle", return_value=None)
    @patch("shopman.shop.services.availability._load_session_holds_for_sku")
    @patch("shopman.shop.services.availability.get_adapter")
    @patch("shopman.shop.services.availability.check")
    def test_reconcile_shrink_releases_fifo_no_overshoot(
        self, mock_check, mock_get_adapter, mock_load_sku, mock_expand,
    ):
        """Shrink that lands exactly on a hold boundary → no compensating hold."""
        from shopman.shop.services.availability import reconcile

        mock_load_sku.return_value = [
            ("hold:A", Decimal("2")),  # FIFO first
            ("hold:B", Decimal("3")),
        ]
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter

        # current=5, new=3 → diff=2 → release A (2), released=2, overshoot=0
        result = reconcile("X", Decimal("3"), session_key="s1", channel_ref="web")

        assert result["ok"] is True
        adapter.release_holds.assert_called_once_with(["hold:A"])
        adapter.create_hold.assert_not_called()

    @patch("shopman.shop.services.availability._expand_if_bundle", return_value=None)
    @patch("shopman.shop.services.availability._load_session_holds_for_sku")
    @patch("shopman.shop.services.availability.get_adapter")
    @patch("shopman.shop.services.availability.check")
    def test_reconcile_shrink_with_overshoot_creates_compensating_hold(
        self, mock_check, mock_get_adapter, mock_load_sku, mock_expand,
    ):
        """Shrink that overshoots last hold → compensating hold for leftover."""
        from shopman.shop.services.availability import reconcile

        mock_load_sku.return_value = [
            ("hold:A", Decimal("2")),
            ("hold:B", Decimal("3")),  # total=5
            ("hold:C", Decimal("2")),
        ]
        adapter = MagicMock()
        adapter.create_hold.return_value = {
            "success": True, "hold_id": "hold:COMP",
        }
        mock_get_adapter.return_value = adapter

        # current=7, new=4 → diff=3 → release A(2), B(3) (released=5,
        # overshoot=2) → compensating hold for 2.
        result = reconcile("X", Decimal("4"), session_key="s1", channel_ref="web")

        assert result["ok"] is True
        adapter.release_holds.assert_called_once_with(["hold:A", "hold:B"])
        adapter.create_hold.assert_called_once()
        kwargs = adapter.create_hold.call_args.kwargs
        assert kwargs["qty"] == Decimal("2")
        assert result["hold_ids"] == ["hold:COMP"]

    @patch("shopman.shop.services.availability._expand_if_bundle", return_value=None)
    @patch("shopman.shop.services.availability._load_session_holds_for_sku")
    @patch("shopman.shop.services.availability.get_adapter")
    @patch("shopman.shop.services.availability.check")
    def test_reconcile_zero_releases_all(
        self, mock_check, mock_get_adapter, mock_load_sku, mock_expand,
    ):
        """remove_item → reconcile(sku, 0) → release every session hold."""
        from shopman.shop.services.availability import reconcile

        mock_load_sku.return_value = [
            ("hold:A", Decimal("2")),
            ("hold:B", Decimal("3")),
        ]
        adapter = MagicMock()
        mock_get_adapter.return_value = adapter

        result = reconcile("X", Decimal("0"), session_key="s1", channel_ref="web")

        assert result["ok"] is True
        adapter.release_holds.assert_called_once_with(["hold:A", "hold:B"])
        adapter.create_hold.assert_not_called()


# ══════════════════════════════════════════════════════════════════════
# CartService integration — update_qty / remove_item invoke reconcile
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestCartReconcileIntegration:
    """Minimal integration: CartService wiring calls reconcile with the
    line's SKU and the absolute new qty (not a delta).
    """

    def _setup_cart(self):
        from shopman.orderman.models import Session

        channel, _ = Channel.objects.get_or_create(
            ref="web",
            defaults={
                "name": "Web",
                "kind": "web",
            },
        )
        session = Session.objects.create(
            session_key="sess-test-1",
            channel_ref=channel.ref,
            pricing_policy="internal",
            edit_policy="open",
            data={},
        )
        # Manually place a line in session.items (what ModifyService would do).
        session.update_items([
            {
                "line_id": "line-1",
                "sku": "X",
                "qty": 2,
                "unit_price_q": 1000,
                "line_total_q": 2000,
            },
        ])
        return channel, session

    def _request_with_session(self, session_key):
        request = MagicMock()
        request.session = {"cart_session_key": session_key}
        return request

    @patch("shopman.storefront.cart.ModifyService")
    @patch("shopman.storefront.cart.availability")
    def test_update_qty_calls_reconcile_with_absolute_new_qty(
        self, mock_availability, mock_modify,
    ):
        from shopman.storefront.cart import CartService

        self._setup_cart()
        request = self._request_with_session("sess-test-1")

        mock_availability.reconcile.return_value = {
            "ok": True,
            "hold_ids": [],
            "released_ids": [],
            "available_qty": Decimal("0"),
            "is_paused": False,
            "error_code": None,
            "substitutes": [],
        }

        CartService.update_qty(request, "line-1", 5)

        mock_availability.reconcile.assert_called_once()
        call_kwargs = mock_availability.reconcile.call_args.kwargs
        assert call_kwargs["sku"] == "X"
        assert call_kwargs["new_qty"] == Decimal("5")
        assert call_kwargs["session_key"] == "sess-test-1"

    @patch("shopman.storefront.cart.ModifyService")
    @patch("shopman.storefront.cart.availability")
    def test_update_qty_shortage_raises_and_does_not_modify(
        self, mock_availability, mock_modify,
    ):
        from shopman.storefront.cart import CartService, CartUnavailableError

        self._setup_cart()
        request = self._request_with_session("sess-test-1")

        mock_availability.reconcile.return_value = {
            "ok": False,
            "hold_ids": [],
            "released_ids": [],
            "available_qty": Decimal("3"),
            "is_paused": False,
            "error_code": "insufficient_stock",
            "substitutes": [],
        }

        with pytest.raises(CartUnavailableError) as excinfo:
            CartService.update_qty(request, "line-1", 999)

        assert excinfo.value.sku == "X"
        mock_modify.modify_session.assert_not_called()

    @patch("shopman.storefront.cart.ModifyService")
    @patch("shopman.storefront.cart.availability")
    def test_remove_item_calls_reconcile_with_zero(
        self, mock_availability, mock_modify,
    ):
        from shopman.storefront.cart import CartService

        self._setup_cart()
        request = self._request_with_session("sess-test-1")

        mock_availability.reconcile.return_value = {
            "ok": True,
            "hold_ids": [],
            "released_ids": ["hold:A"],
            "available_qty": Decimal("0"),
            "is_paused": False,
            "error_code": None,
            "substitutes": [],
        }

        CartService.remove_item(request, "line-1")

        mock_availability.reconcile.assert_called_once()
        call_kwargs = mock_availability.reconcile.call_args.kwargs
        assert call_kwargs["sku"] == "X"
        assert call_kwargs["new_qty"] == Decimal("0")
        mock_modify.modify_session.assert_called_once()
