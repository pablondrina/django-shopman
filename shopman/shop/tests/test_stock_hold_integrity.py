"""
Stock hold integrity tests — P5 Framework Elevation.

Proves the full stock hold pipeline works correctly:
  - hold() with correct quantities → hold_ids populated with right qty
  - bundle expansion → each component held with correct qty
  - partial stock (adapter returns failure) → graceful handling, hold_ids reflects partial
  - qty mismatch detection by _verify_holds (SKU presence check)

Note: _verify_holds() checks SKU presence only, not quantity. Quantity integrity
is guaranteed by the adapter at hold time (adapter rejects insufficient qty via
success=False). These tests document both the guarantee and its scope.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TransactionTestCase as TestCase
from shopman.orderman.ids import generate_idempotency_key, generate_session_key
from shopman.orderman.models import Order, Session
from shopman.orderman.services import CommitService

from shopman.shop.models import Channel

# ── Helpers ──────────────────────────────────────────────────────────

def _make_channel(ref, config=None):
    return Channel.objects.create(
        ref=ref, name=ref, kind="web",
        config=config or {
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": False},
        },
    )


def _make_session(channel, items):
    return Session.objects.create(
        session_key=generate_session_key(),
        channel_ref=channel.ref,
        state="open",
        items=items,
    )


def _commit(session, channel):
    return CommitService.commit(
        session_key=session.session_key,
        channel_ref=channel.ref,
        idempotency_key=generate_idempotency_key(),
    )


def _make_stock_adapter(holds=None):
    """Return a mock stock adapter that returns success for create_hold."""
    adapter = MagicMock()
    adapter.find_holds_by_reference.return_value = []  # no session holds

    _call_count = [0]
    _holds = holds or {}

    def _create_hold(sku, qty, reference=None, **kwargs):
        hold_id = _holds.get(sku, f"H-{sku}-auto")
        return {"success": True, "hold_id": hold_id}

    adapter.create_hold.side_effect = _create_hold
    adapter.release_holds.return_value = None
    adapter.retag_hold_reference.return_value = None
    return adapter


_LIFECYCLE_PATCHES = [
    "shopman.shop.services.notification.send",
    "shopman.shop.services.customer.ensure",
    "shopman.shop.services.loyalty.redeem",
    "shopman.shop.services.payment.initiate",
    "shopman.shop.services.availability.decide",
    "shopman.shop.services.fulfillment.create",
]

_AVAIL_OK = {
    "approved": True,
    "sku": "CROIS-01",
    "requested_qty": Decimal("1"),
    "available_qty": Decimal("999"),
    "reason_code": None,
    "is_paused": False,
    "is_planned": False,
    "target_date": None,
    "failed_sku": None,
    "source": "stock.untracked",
    "untracked": True,
}


def _start_lifecycle_patches(extra_patches=None):
    patchers = []
    mocks = {}
    for target in (_LIFECYCLE_PATCHES + (extra_patches or [])):
        ret = _AVAIL_OK if "availability" in target else None
        p = patch(target, return_value=ret)
        try:
            m = p.start()
            patchers.append(p)
            mocks[target.rsplit(".", 1)[-1]] = m
        except AttributeError:
            pass
    return patchers, mocks


def _stop_patches(patchers):
    for p in patchers:
        try:
            p.stop()
        except RuntimeError:
            pass


# ── P5-1: Hold with correct quantities ───────────────────────────────

class TestHoldCorrectQuantities(TestCase):
    """hold() with correct quantities → hold_ids populated for all items."""

    def setUp(self):
        self.channel = _make_channel("hold-qty-1")
        self.patchers, self.mocks = _start_lifecycle_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    @patch("shopman.shop.services.stock.get_adapter")
    @patch("shopman.shop.services.stock._expand_if_bundle")
    def test_single_item_hold_creates_hold_id(self, mock_expand, mock_get_adapter):
        mock_expand.side_effect = lambda sku, qty: [{"sku": sku, "qty": qty}]
        mock_adapter = _make_stock_adapter(holds={"CROIS-01": "H-001"})
        mock_get_adapter.return_value = mock_adapter

        session = _make_session(self.channel, items=[
            {"sku": "CROIS-01", "qty": 2, "unit_price_q": 500, "line_id": "L1"},
        ])
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result.order_ref)

        hold_ids = order.data.get("hold_ids", [])
        self.assertEqual(len(hold_ids), 1)
        self.assertEqual(hold_ids[0]["sku"], "CROIS-01")
        self.assertEqual(hold_ids[0]["hold_id"], "H-001")
        self.assertAlmostEqual(float(hold_ids[0]["qty"]), 2.0)

    @patch("shopman.shop.services.stock.get_adapter")
    @patch("shopman.shop.services.stock._expand_if_bundle")
    def test_multi_item_hold_creates_all_hold_ids(self, mock_expand, mock_get_adapter):
        mock_expand.side_effect = lambda sku, qty: [{"sku": sku, "qty": qty}]
        mock_adapter = _make_stock_adapter(holds={
            "CROIS-01": "H-001",
            "CAFE-01": "H-002",
        })
        mock_get_adapter.return_value = mock_adapter

        session = _make_session(self.channel, items=[
            {"sku": "CROIS-01", "qty": 2, "unit_price_q": 500, "line_id": "L1"},
            {"sku": "CAFE-01",  "qty": 1, "unit_price_q": 800, "line_id": "L2"},
        ])
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result.order_ref)

        hold_ids = order.data.get("hold_ids", [])
        self.assertEqual(len(hold_ids), 2)
        skus = {h["sku"] for h in hold_ids}
        self.assertIn("CROIS-01", skus)
        self.assertIn("CAFE-01", skus)

    @patch("shopman.shop.services.stock.get_adapter")
    @patch("shopman.shop.services.stock._expand_if_bundle")
    def test_hold_qty_matches_ordered_qty(self, mock_expand, mock_get_adapter):
        """Qty in hold_ids must match ordered qty exactly (no session holds to adopt)."""
        mock_expand.side_effect = lambda sku, qty: [{"sku": sku, "qty": qty}]
        mock_adapter = MagicMock()
        mock_adapter.find_holds_by_reference.return_value = []
        created_holds = []

        def _create_hold(sku, qty, reference=None, **kwargs):
            hold_id = f"H-{sku}"
            created_holds.append({"sku": sku, "qty": float(qty), "hold_id": hold_id})
            return {"success": True, "hold_id": hold_id}

        mock_adapter.create_hold.side_effect = _create_hold
        mock_adapter.release_holds.return_value = None
        mock_adapter.retag_hold_reference.return_value = None
        mock_get_adapter.return_value = mock_adapter

        session = _make_session(self.channel, items=[
            {"sku": "PAO-01", "qty": 5, "unit_price_q": 100, "line_id": "L1"},
        ])
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result.order_ref)

        hold_ids = order.data.get("hold_ids", [])
        self.assertEqual(len(hold_ids), 1)
        self.assertAlmostEqual(float(hold_ids[0]["qty"]), 5.0)

        # Adapter received the correct qty
        self.assertEqual(len(created_holds), 1)
        self.assertAlmostEqual(created_holds[0]["qty"], 5.0)


# ── P5-2: Bundle expansion → each component held with correct qty ─────

class TestBundleExpansion(TestCase):
    """Bundle items are expanded into components, each held with correct qty."""

    def setUp(self):
        self.channel = _make_channel("bundle-1")
        self.patchers, self.mocks = _start_lifecycle_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    @patch("shopman.shop.services.stock.get_adapter")
    @patch("shopman.shop.services.stock._expand_if_bundle")
    def test_bundle_expanded_into_components(self, mock_expand, mock_get_adapter):
        """A bundle SKU expands into 2 components, each getting its own hold."""
        # Bundle: COMBO-01 (qty=1) → CROIS-01 (qty=2) + CAFE-01 (qty=1)
        def _expand(sku, qty):
            if sku == "COMBO-01":
                return [
                    {"sku": "CROIS-01", "qty": Decimal("2") * qty},
                    {"sku": "CAFE-01",  "qty": Decimal("1") * qty},
                ]
            return [{"sku": sku, "qty": qty}]

        mock_expand.side_effect = _expand

        mock_adapter = MagicMock()
        mock_adapter.find_holds_by_reference.return_value = []
        created = {}

        def _create_hold(sku, qty, reference=None, **kwargs):
            created[sku] = float(qty)
            return {"success": True, "hold_id": f"H-{sku}"}

        mock_adapter.create_hold.side_effect = _create_hold
        mock_adapter.release_holds.return_value = None
        mock_adapter.retag_hold_reference.return_value = None
        mock_get_adapter.return_value = mock_adapter

        session = _make_session(self.channel, items=[
            {"sku": "COMBO-01", "qty": 1, "unit_price_q": 1200, "line_id": "L1"},
        ])
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result.order_ref)

        hold_ids = order.data.get("hold_ids", [])
        # Bundle produces 2 holds (one per component)
        self.assertEqual(len(hold_ids), 2)
        hold_skus = {h["sku"] for h in hold_ids}
        self.assertIn("CROIS-01", hold_skus)
        self.assertIn("CAFE-01", hold_skus)

        # Component quantities are correct
        self.assertAlmostEqual(created.get("CROIS-01", 0), 2.0)
        self.assertAlmostEqual(created.get("CAFE-01", 0), 1.0)

    @patch("shopman.shop.services.stock.get_adapter")
    @patch("shopman.shop.services.stock._expand_if_bundle")
    def test_bundle_qty_multiplied_by_ordered_qty(self, mock_expand, mock_get_adapter):
        """Ordering 2 bundles → component qtys multiplied by 2."""
        def _expand(sku, qty):
            if sku == "COMBO-01":
                return [{"sku": "CROIS-01", "qty": Decimal("2") * qty}]
            return [{"sku": sku, "qty": qty}]

        mock_expand.side_effect = _expand

        mock_adapter = MagicMock()
        mock_adapter.find_holds_by_reference.return_value = []
        created = {}

        def _create_hold(sku, qty, reference=None, **kwargs):
            created[sku] = float(qty)
            return {"success": True, "hold_id": f"H-{sku}"}

        mock_adapter.create_hold.side_effect = _create_hold
        mock_adapter.release_holds.return_value = None
        mock_adapter.retag_hold_reference.return_value = None
        mock_get_adapter.return_value = mock_adapter

        session = _make_session(self.channel, items=[
            {"sku": "COMBO-01", "qty": 2, "unit_price_q": 1200, "line_id": "L1"},
        ])
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result.order_ref)

        # CROIS-01: 2 (per combo) × 2 (ordered) = 4
        self.assertAlmostEqual(created.get("CROIS-01", 0), 4.0)


# ── P5-3: Partial stock — adapter rejects one SKU ────────────────────

class TestPartialStock(TestCase):
    """When adapter returns success=False for a SKU, that hold is skipped."""

    def setUp(self):
        self.channel = _make_channel("partial-1")
        self.patchers, self.mocks = _start_lifecycle_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    @patch("shopman.shop.services.stock.get_adapter")
    @patch("shopman.shop.services.stock._expand_if_bundle")
    def test_partial_hold_skips_failed_sku(self, mock_expand, mock_get_adapter):
        """Adapter failure for one SKU → that SKU not in hold_ids, others are."""
        mock_expand.side_effect = lambda sku, qty: [{"sku": sku, "qty": qty}]

        mock_adapter = MagicMock()
        mock_adapter.find_holds_by_reference.return_value = []

        def _create_hold(sku, qty, reference=None, **kwargs):
            if sku == "OOS-SKU":
                return {"success": False, "hold_id": None, "error_code": "out_of_stock"}
            return {"success": True, "hold_id": f"H-{sku}"}

        mock_adapter.create_hold.side_effect = _create_hold
        mock_adapter.release_holds.return_value = None
        mock_adapter.retag_hold_reference.return_value = None
        mock_get_adapter.return_value = mock_adapter

        session = _make_session(self.channel, items=[
            {"sku": "CROIS-01", "qty": 2, "unit_price_q": 500, "line_id": "L1"},
            {"sku": "OOS-SKU",  "qty": 1, "unit_price_q": 800, "line_id": "L2"},
        ])
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result.order_ref)

        hold_ids = order.data.get("hold_ids", [])
        held_skus = {h["sku"] for h in hold_ids}

        # CROIS-01 was held successfully
        self.assertIn("CROIS-01", held_skus)
        # OOS-SKU was NOT added (adapter rejected it)
        self.assertNotIn("OOS-SKU", held_skus)


# ── P5-4: _verify_holds — SKU presence check ─────────────────────────

class TestVerifyHolds(TestCase):
    """_verify_holds() catches missing SKUs. Documents quantity check scope."""

    def setUp(self):
        # Use check_on_commit=True so _verify_holds runs
        self.channel = _make_channel("verify-1", config={
            "confirmation": {"mode": "immediate"},
            "payment": {"method": "cash", "timing": "external"},
            "stock": {"check_on_commit": True},
        })
        self.patchers, self.mocks = _start_lifecycle_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    @patch("shopman.shop.services.stock.get_adapter")
    @patch("shopman.shop.services.stock._expand_if_bundle")
    def test_missing_sku_cancels_order(self, mock_expand, mock_get_adapter):
        """When hold() fails for a SKU, _verify_holds cancels the order."""
        mock_expand.side_effect = lambda sku, qty: [{"sku": sku, "qty": qty}]

        mock_adapter = MagicMock()
        mock_adapter.find_holds_by_reference.return_value = []

        def _create_hold(sku, qty, reference=None, **kwargs):
            if sku == "MISSING-SKU":
                # Adapter rejects → hold not added to hold_ids
                return {"success": False, "hold_id": None, "error_code": "out_of_stock"}
            return {"success": True, "hold_id": f"H-{sku}"}

        mock_adapter.create_hold.side_effect = _create_hold
        mock_adapter.release_holds.return_value = None
        mock_adapter.retag_hold_reference.return_value = None
        mock_get_adapter.return_value = mock_adapter

        session = _make_session(self.channel, items=[
            {"sku": "CROIS-01",   "qty": 2, "unit_price_q": 500, "line_id": "L1"},
            {"sku": "MISSING-SKU","qty": 1, "unit_price_q": 800, "line_id": "L2"},
        ])
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result.order_ref)

        # _verify_holds sees MISSING-SKU not in hold_ids → cancels order
        self.assertEqual(order.status, Order.Status.CANCELLED)

    @patch("shopman.shop.services.stock.get_adapter")
    @patch("shopman.shop.services.stock._expand_if_bundle")
    def test_all_skus_held_order_proceeds(self, mock_expand, mock_get_adapter):
        """When all SKUs are held, _verify_holds passes and order proceeds."""
        mock_expand.side_effect = lambda sku, qty: [{"sku": sku, "qty": qty}]
        mock_adapter = _make_stock_adapter(holds={"CROIS-01": "H-001"})
        mock_get_adapter.return_value = mock_adapter

        session = _make_session(self.channel, items=[
            {"sku": "CROIS-01", "qty": 2, "unit_price_q": 500, "line_id": "L1"},
        ])
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result.order_ref)

        # Order confirmed (immediate mode), not cancelled
        self.assertEqual(order.status, Order.Status.CONFIRMED)

    def test_verify_holds_qty_scope(self):
        """
        Document: _verify_holds() checks SKU PRESENCE only, not quantity.

        If an adapter returns a partial hold (e.g. hold for 1 unit when 5 were
        requested), _verify_holds will still pass because the SKU is present.
        The quantity guarantee lives in the adapter: adapter.create_hold() returns
        success=False if the requested qty is not available, and hold() skips that
        hold (leaving the SKU absent from hold_ids, which _verify_holds catches).
        """
        from shopman.shop.lifecycle import _verify_holds

        # Build a minimal order-like object with mismatched qty
        class FakeOrder:
            data = {"hold_ids": [{"sku": "A", "hold_id": "H-1", "qty": 1}]}
            snapshot = {"items": [{"sku": "A", "qty": 5}]}
            channel_ref = "test"
            ref = "ORD-TEST"
            status = "new"

            def transition_status(self, *a, **kw): ...

        with patch("shopman.shop.lifecycle.stock.release"), \
             patch("shopman.shop.lifecycle._create_alert"):
            # SKU present → _verify_holds returns True even with qty mismatch
            result = _verify_holds(FakeOrder())
            self.assertTrue(result)


# ── P5-5: Session holds adoption ─────────────────────────────────────

class TestSessionHoldsAdoption(TestCase):
    """Session holds created at cart-add time are adopted during commit."""

    def setUp(self):
        self.channel = _make_channel("adopt-1")
        self.patchers, self.mocks = _start_lifecycle_patches()

    def tearDown(self):
        _stop_patches(self.patchers)

    @patch("shopman.shop.services.stock.get_adapter")
    @patch("shopman.shop.services.stock._expand_if_bundle")
    def test_session_holds_adopted_before_fresh_create(self, mock_expand, mock_get_adapter):
        """Existing session holds are adopted (retag) rather than creating new ones."""
        mock_expand.side_effect = lambda sku, qty: [{"sku": sku, "qty": qty}]

        mock_adapter = MagicMock()
        # Simulate one session hold for CROIS-01 with qty=2
        mock_adapter.find_holds_by_reference.return_value = [
            ("SH-001", "CROIS-01", Decimal("2")),
        ]
        mock_adapter.retag_hold_reference.return_value = None
        mock_adapter.release_holds.return_value = None
        mock_adapter.create_hold.return_value = {"success": True, "hold_id": "H-NEW"}
        mock_get_adapter.return_value = mock_adapter

        session = _make_session(self.channel, items=[
            {"sku": "CROIS-01", "qty": 2, "unit_price_q": 500, "line_id": "L1"},
        ])
        result = _commit(session, self.channel)
        order = Order.objects.get(ref=result.order_ref)

        hold_ids = order.data.get("hold_ids", [])
        # Session hold was adopted (not a fresh create)
        self.assertEqual(len(hold_ids), 1)
        self.assertEqual(hold_ids[0]["hold_id"], "SH-001")
        # No fresh hold created for this SKU
        mock_adapter.create_hold.assert_not_called()
        # Retag was called to associate with order
        mock_adapter.retag_hold_reference.assert_called_once()
