"""
Tests for shopman.services — each service testable in isolation.

Uses mocking for Core services and adapters to ensure isolation.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from shopman.orderman.models import Directive

# ── helpers ──


def _make_order(**overrides):
    """Create a mock Order object."""
    order = MagicMock()
    order.ref = overrides.get("ref", "ORD-001")
    order.total_q = overrides.get("total_q", 5000)
    order.status = overrides.get("status", "new")
    order.handle_type = overrides.get("handle_type", "")
    order.handle_ref = overrides.get("handle_ref", "")
    order.data = overrides.get("data", {})
    order.snapshot = overrides.get("snapshot", {"items": [], "data": {}})

    channel = MagicMock()
    channel.ref = overrides.get("channel_ref", "web")
    channel.name = "Web"
    channel.config = overrides.get("channel_config", {})
    order.channel_ref = channel.ref

    # items manager
    items_qs = MagicMock()
    items_list = overrides.get("items_list", [])
    items_qs.all.return_value = items_list
    items_qs.__iter__ = lambda self: iter(items_list)
    items_qs.count.return_value = len(items_list)
    order.items = items_qs

    return order


def _make_item(sku="PAO-001", name="Pão Francês", qty=5, unit_price_q=100, line_total_q=500, meta=None):
    item = MagicMock()
    item.sku = sku
    item.name = name
    item.qty = Decimal(str(qty))
    item.unit_price_q = unit_price_q
    item.line_total_q = line_total_q
    item.meta = meta or {}
    return item


# ══════════════════════════════════════════════════════════════════════
# services/availability.py
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAvailabilityListingMembership:
    """`availability.check` honors per-channel listing membership.

    The check fails with `error_code=not_in_listing` when a SKU is not in
    the listing of the channel that's asking — even if Stockman has stock.
    """

    def _make_channel(self, ref="ifood"):
        """Channel.ref == Listing.ref by convention."""
        from shopman.models import Channel
        return Channel.objects.create(
            ref=ref,
            name=ref.upper(),
        )

    def _make_product(self, sku="PAO-001", paused=False):
        from shopman.offerman.models import Product
        return Product.objects.create(
            sku=sku,
            name=sku,
            base_price_q=500,
            is_published=not paused,
            is_available=not paused,
        )

    def _make_listing(self, ref):
        """Create a listing with ref matching a channel ref (convention: listing.ref == channel.ref)."""
        from shopman.offerman.models import Listing
        return Listing.objects.create(
            ref=ref, name=ref, is_active=True, priority=10,
        )

    def _publish(self, listing, product, *, published=True, available=True):
        from shopman.offerman.models import ListingItem
        return ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=500,
            is_published=published,
            is_available=available,
        )

    def test_rejects_sku_absent_from_channel_listing(self):
        """Product exists, has stock, but is NOT in the channel's listing → reject."""
        from shopman.services import availability

        self._make_channel(ref="ifood")
        self._make_product(sku="PAO-001")
        # listing.ref == channel.ref by convention; exists but no ListingItem for this product
        self._make_listing("ifood")

        result = availability.check("PAO-001", Decimal("1"), channel_ref="ifood")

        assert result["ok"] is False
        assert result["error_code"] == "not_in_listing"
        assert result["available_qty"] == Decimal("0")

    def test_rejects_unpublished_listing_item(self):
        """ListingItem exists but is_published=False → reject."""
        from shopman.services import availability

        self._make_channel(ref="ifood")
        product = self._make_product(sku="PAO-001")
        listing = self._make_listing("ifood")
        self._publish(listing, product, published=False, available=True)

        result = availability.check("PAO-001", Decimal("1"), channel_ref="ifood")

        assert result["ok"] is False
        assert result["error_code"] == "not_in_listing"

    def test_passes_when_published_in_channel_listing(self):
        """ListingItem published+available → check proceeds to Stockman layer.

        Without seeded Quants the SKU is treated as `untracked` (ok=True),
        which is the documented behavior — what we're proving here is that
        the listing gate did NOT veto the call.
        """
        from shopman.services import availability

        self._make_channel(ref="ifood")
        product = self._make_product(sku="PAO-001")
        listing = self._make_listing("ifood")
        self._publish(listing, product, published=True, available=True)

        result = availability.check("PAO-001", Decimal("1"), channel_ref="ifood")

        assert result["ok"] is True
        assert result.get("error_code") is None

    def test_skips_listing_check_when_channel_has_no_listing(self):
        """Channels without a Listing configured skip the listing gate."""
        from shopman.services import availability

        self._make_channel(ref="pos-internal")
        self._make_product(sku="PAO-001")
        # No Listing with ref="pos-internal" exists → gate skipped

        result = availability.check("PAO-001", Decimal("1"), channel_ref="pos-internal")

        assert result["ok"] is True
        assert result.get("error_code") is None

    def test_rejects_below_min_qty(self):
        """ListingItem.min_qty enforced: qty < min_qty → ok=False, error_code=below_min_qty."""
        from shopman.offerman.models import ListingItem
        from shopman.services import availability

        self._make_channel(ref="ifood")
        product = self._make_product(sku="PAO-001")
        listing = self._make_listing("ifood")
        # min_qty=24 (e.g., pão francês in dozens)
        ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=500,
            is_published=True,
            is_available=True,
            min_qty=Decimal("24"),
        )

        # Order qty=1 < min_qty=24 → reject
        result = availability.check("PAO-001", Decimal("1"), channel_ref="ifood")

        assert result["ok"] is False
        assert result["error_code"] == "below_min_qty"
        assert result["available_qty"] == Decimal("24")

    def test_passes_when_qty_meets_min_qty(self):
        """qty >= min_qty → listing gate passes."""
        from shopman.offerman.models import ListingItem
        from shopman.services import availability

        self._make_channel(ref="ifood")
        product = self._make_product(sku="PAO-001")
        listing = self._make_listing("ifood")
        ListingItem.objects.create(
            listing=listing,
            product=product,
            price_q=500,
            is_published=True,
            is_available=True,
            min_qty=Decimal("5"),
        )

        # qty=5 == min_qty=5 → passes listing gate (Stockman treats as untracked)
        result = availability.check("PAO-001", Decimal("5"), channel_ref="ifood")

        assert result.get("error_code") != "below_min_qty"


# ══════════════════════════════════════════════════════════════════════
# services/stock.py
# ══════════════════════════════════════════════════════════════════════


class TestStockService:

    @patch("shopman.services.stock._load_session_holds")
    @patch("shopman.services.stock.get_adapter")
    def test_hold_simple_items_creates_hold(
        self, mock_get_adapter, mock_load,
    ):
        from shopman.services.stock import hold

        adapter = MagicMock()
        adapter.expand_bundle.side_effect = Exception("NOT_A_BUNDLE")
        adapter.create_hold.return_value = {"success": True, "hold_id": "hold:1"}
        mock_get_adapter.return_value = adapter
        mock_load.return_value = {}  # no session holds to adopt

        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": "5"}], "data": {}},
        )

        hold(order)

        adapter.create_hold.assert_called_once()
        assert order.data["hold_ids"][0]["hold_id"] == "hold:1"
        order.save.assert_called()

    @patch("shopman.services.stock._load_session_holds")
    @patch("shopman.services.stock.get_adapter")
    def test_hold_expands_bundles(self, mock_get_adapter, mock_load):
        from shopman.services.stock import hold

        adapter = MagicMock()
        adapter.expand_bundle.return_value = [
            {"sku": "COMP-A", "qty": Decimal("2")},
            {"sku": "COMP-B", "qty": Decimal("3")},
        ]
        adapter.create_hold.side_effect = [
            {"success": True, "hold_id": "hold:1"},
            {"success": True, "hold_id": "hold:2"},
        ]
        mock_get_adapter.return_value = adapter
        mock_load.return_value = {}

        order = _make_order(
            snapshot={"items": [{"sku": "BUNDLE-1", "qty": "1"}], "data": {}},
        )

        hold(order)

        assert adapter.create_hold.call_count == 2
        assert len(order.data["hold_ids"]) == 2

    @patch("shopman.services.stock._retag_hold_for_order")
    @patch("shopman.services.stock._load_session_holds")
    @patch("shopman.services.stock.get_adapter")
    def test_hold_adopts_session_holds(
        self, mock_get_adapter, mock_load, mock_retag,
    ):
        from shopman.services.stock import hold

        adapter = MagicMock()
        adapter.expand_bundle.side_effect = Exception("NOT_A_BUNDLE")
        mock_get_adapter.return_value = adapter
        # Session has one hold of exactly the required qty — fully satisfies.
        mock_load.return_value = {"PAO-001": [("hold:42", Decimal("5"))]}

        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": "5"}], "data": {}},
        )
        order.session_key = "sess-1"

        hold(order)

        # Adopted, not freshly created
        adapter.create_hold.assert_not_called()
        mock_retag.assert_called_once_with("hold:42", order.ref)
        assert order.data["hold_ids"][0]["hold_id"] == "hold:42"

    @patch("shopman.services.stock._retag_hold_for_order")
    @patch("shopman.services.stock._load_session_holds")
    @patch("shopman.services.stock.get_adapter")
    def test_hold_adopts_multiple_session_holds_summing_qty(
        self, mock_get_adapter, mock_load, mock_retag,
    ):
        """Two holds of qty=2 each should both be adopted to cover qty=4."""
        from shopman.services.stock import hold

        adapter = MagicMock()
        adapter.expand_bundle.side_effect = Exception("NOT_A_BUNDLE")
        mock_get_adapter.return_value = adapter
        mock_load.return_value = {
            "PAO-001": [
                ("hold:10", Decimal("2")),
                ("hold:11", Decimal("2")),
            ],
        }

        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": "4"}], "data": {}},
        )
        order.session_key = "sess-1"

        hold(order)

        adapter.create_hold.assert_not_called()
        assert mock_retag.call_count == 2
        hold_entries = order.data["hold_ids"]
        assert len(hold_entries) == 2
        assert {e["hold_id"] for e in hold_entries} == {"hold:10", "hold:11"}
        assert sum(Decimal(str(e["qty"])) for e in hold_entries) == Decimal("4")

    @patch("shopman.services.stock._retag_hold_for_order")
    @patch("shopman.services.stock._load_session_holds")
    @patch("shopman.services.stock.get_adapter")
    def test_hold_adopts_session_holds_and_creates_fresh_for_remainder(
        self, mock_get_adapter, mock_load, mock_retag,
    ):
        """Session covers qty=2, required=5 → adopt 2 + create 3 fresh."""
        from shopman.services.stock import hold

        adapter = MagicMock()
        adapter.expand_bundle.side_effect = Exception("NOT_A_BUNDLE")
        adapter.create_hold.return_value = {"success": True, "hold_id": "hold:21"}
        mock_get_adapter.return_value = adapter
        mock_load.return_value = {
            "PAO-001": [("hold:20", Decimal("2"))],
        }

        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": "5"}], "data": {}},
        )
        order.session_key = "sess-1"

        hold(order)

        adapter.create_hold.assert_called_once()
        # Fresh hold is for remainder = 5 - 2 = 3
        call_kwargs = adapter.create_hold.call_args.kwargs
        assert call_kwargs["qty"] == Decimal("3")

        hold_entries = order.data["hold_ids"]
        assert len(hold_entries) == 2
        assert {e["hold_id"] for e in hold_entries} == {"hold:20", "hold:21"}

    @patch("shopman.services.stock.get_adapter")
    def test_fulfill_calls_adapter(self, mock_get_adapter):
        from shopman.services.stock import fulfill

        adapter = MagicMock()
        adapter.fulfill_hold.return_value = {"success": True}
        mock_get_adapter.return_value = adapter

        order = _make_order(data={
            "hold_ids": [
                {"hold_id": "hold:1", "sku": "PAO-001", "qty": 5},
                {"hold_id": "hold:2", "sku": "PAO-002", "qty": 3},
            ],
        })

        fulfill(order)

        assert adapter.fulfill_hold.call_count == 2

    @patch("shopman.services.stock.get_adapter")
    def test_release_calls_adapter(self, mock_get_adapter):
        from shopman.services.stock import release

        adapter = MagicMock()
        mock_get_adapter.return_value = adapter

        order = _make_order(data={
            "hold_ids": [{"hold_id": "hold:1", "sku": "PAO-001", "qty": 5}],
        })

        release(order)

        adapter.release_holds.assert_called_once_with(["hold:1"])

    @patch("shopman.services.stock.get_adapter")
    def test_revert_calls_adapter(self, mock_get_adapter):
        from shopman.services.stock import revert

        adapter = MagicMock()
        mock_get_adapter.return_value = adapter

        item = _make_item()
        order = _make_order(items_list=[item])

        revert(order)

        adapter.receive_return.assert_called_once()

    def test_hold_skips_empty_items(self):
        from shopman.services.stock import hold

        order = _make_order(snapshot={"items": [], "data": {}})
        hold(order)
        order.save.assert_not_called()


# ══════════════════════════════════════════════════════════════════════
# services/payment.py
# ══════════════════════════════════════════════════════════════════════


class TestPaymentService:

    @patch("shopman.services.payment.get_adapter")
    def test_initiate_pix(self, mock_get_adapter):
        from shopman.adapters.payment_types import PaymentIntent
        from shopman.services.payment import initiate

        adapter = MagicMock()
        adapter.create_intent.return_value = PaymentIntent(
            intent_ref="INT-001",
            status="pending",
            amount_q=5000,
            metadata={"qrcode": "QR123", "brcode": "PIX123"},
        )
        mock_get_adapter.return_value = adapter

        order = _make_order(data={"payment": {"method": "pix"}}, total_q=5000)

        initiate(order)

        adapter.create_intent.assert_called_once()
        call_kwargs = adapter.create_intent.call_args.kwargs
        assert call_kwargs["order_ref"] == order.ref
        assert call_kwargs["amount_q"] == 5000
        assert call_kwargs["method"] == "pix"
        assert order.data["payment"]["intent_ref"] == "INT-001"
        assert order.data["payment"]["qr_code"] == "QR123"
        order.save.assert_called()

    @patch("shopman.services.payment.get_adapter")
    def test_initiate_card(self, mock_get_adapter):
        from shopman.adapters.payment_types import PaymentIntent
        from shopman.services.payment import initiate

        adapter = MagicMock()
        adapter.create_intent.return_value = PaymentIntent(
            intent_ref="INT-002",
            status="pending",
            amount_q=5000,
            client_secret="cs_test_123",
        )
        mock_get_adapter.return_value = adapter

        order = _make_order(data={"payment": {"method": "card"}}, total_q=5000)

        initiate(order)

        assert order.data["payment"]["client_secret"] == "cs_test_123"
        assert order.data["payment"]["intent_ref"] == "INT-002"

    def test_initiate_counter_noop(self):
        from shopman.services.payment import initiate

        order = _make_order(data={"payment": {"method": "cash"}})
        initiate(order)
        order.save.assert_not_called()

    def test_initiate_idempotent(self):
        from shopman.services.payment import initiate

        order = _make_order(data={"payment": {"method": "pix", "intent_ref": "INT-EXISTING"}})
        initiate(order)
        order.save.assert_not_called()

    @patch("shopman.services.payment.get_adapter")
    def test_refund_smart_noop(self, mock_get_adapter):
        from shopman.services.payment import refund

        order = _make_order(data={})
        refund(order)
        mock_get_adapter.assert_not_called()

    @patch("shopman.services.payment._payman_intent_refunded", return_value=False)
    @patch("shopman.services.payment.get_adapter")
    def test_refund_with_intent(self, mock_get_adapter, mock_payman_check):
        from shopman.adapters.payment_types import PaymentResult
        from shopman.services.payment import refund

        adapter = MagicMock()
        adapter.refund.return_value = PaymentResult(success=True)
        mock_get_adapter.return_value = adapter

        order = _make_order(
            data={"payment": {"method": "pix", "intent_ref": "INT-001"}},
        )

        refund(order)

        adapter.refund.assert_called_once()
        # Status is NOT written to order.data — Payman (PaymentService) is canonical
        assert "status" not in order.data["payment"]

    @patch("shopman.services.payment._payman_intent_captured", return_value=False)
    @patch("shopman.services.payment.get_adapter")
    def test_capture(self, mock_get_adapter, mock_payman_check):
        from shopman.adapters.payment_types import PaymentResult
        from shopman.services.payment import capture

        adapter = MagicMock()
        adapter.capture.return_value = PaymentResult(
            success=True,
            transaction_id="TXN-001",
        )
        mock_get_adapter.return_value = adapter

        order = _make_order(
            data={"payment": {"method": "pix", "intent_ref": "INT-001"}},
        )

        capture(order)

        # Status is NOT written to order.data — transaction_id remains as reference
        assert "status" not in order.data["payment"]
        assert order.data["payment"]["transaction_id"] == "TXN-001"


# ══════════════════════════════════════════════════════════════════════
# services/notification.py
# ══════════════════════════════════════════════════════════════════════


class TestNotificationService:

    @pytest.mark.django_db
    def test_send_creates_directive(self):
        from shopman.services.notification import send

        order = _make_order()

        send(order, "order_confirmed")

        directive = Directive.objects.last()
        assert directive is not None
        assert directive.topic == "notification.send"
        assert directive.payload["order_ref"] == "ORD-001"
        assert directive.payload["template"] == "order_confirmed"

    @pytest.mark.django_db
    def test_send_includes_origin_channel(self):
        from shopman.services.notification import send

        order = _make_order(data={"origin_channel": "whatsapp"})

        send(order, "order_confirmed")

        directive = Directive.objects.last()
        assert directive.payload["origin_channel"] == "whatsapp"


class TestNotificationSendHandler:
    """Unit tests for NotificationSendHandler._build_context."""

    def test_build_context_reads_items_from_snapshot(self):
        """Items must come from order.snapshot, not order.data (CommitService never copies them)."""
        from shopman.handlers.notification import NotificationSendHandler

        items = [{"sku": "PAO-001", "name": "Pão Francês", "qty": 2, "line_total_q": 200}]
        order = _make_order(
            snapshot={"items": items, "data": {}},
            data={"fulfillment_type": "pickup"},
        )
        handler = NotificationSendHandler()

        ctx = handler._build_context(order, {"order_ref": "ORD-001"}, "order_confirmed")

        assert ctx["items"] == items, "items must be read from order.snapshot, not order.data"

    def test_build_context_items_empty_when_snapshot_has_none(self):
        """Empty snapshot returns empty items list without error."""
        from shopman.handlers.notification import NotificationSendHandler

        order = _make_order(snapshot={}, data={})
        handler = NotificationSendHandler()

        ctx = handler._build_context(order, {"order_ref": "ORD-001"}, "order_confirmed")

        assert ctx["items"] == []


# ══════════════════════════════════════════════════════════════════════
# services/fulfillment.py
# ══════════════════════════════════════════════════════════════════════


class TestFulfillmentService:

    @pytest.mark.django_db
    def test_create_is_idempotent(self):
        from shopman.services.fulfillment import create

        order = _make_order(data={"fulfillment_created": True})

        result = create(order)

        assert result is None
        order.save.assert_not_called()

    def test_update_enriches_tracking_url(self):
        from shopman.services.fulfillment import update

        fulfillment = MagicMock()
        fulfillment.carrier = ""
        fulfillment.tracking_code = ""
        fulfillment.tracking_url = ""
        fulfillment.order.ref = "ORD-001"

        update(fulfillment, "dispatched", tracking_code="BR123456", carrier="correios")

        assert "rastreamento.correios" in fulfillment.tracking_url
        fulfillment.save.assert_called_once()

    def test_update_preserves_existing_tracking_url(self):
        from shopman.services.fulfillment import update

        fulfillment = MagicMock()
        fulfillment.carrier = "jadlog"
        fulfillment.tracking_code = "JD-001"
        fulfillment.tracking_url = "https://custom.url/track"
        fulfillment.order.ref = "ORD-001"

        update(fulfillment, "delivered")

        assert fulfillment.tracking_url == "https://custom.url/track"


# ══════════════════════════════════════════════════════════════════════
# services/loyalty.py
# ══════════════════════════════════════════════════════════════════════


class TestLoyaltyService:

    @pytest.mark.django_db
    def test_earn_creates_directive(self):
        from shopman.services.loyalty import earn

        order = _make_order(total_q=5000)

        earn(order)

        directive = Directive.objects.last()
        assert directive is not None
        assert directive.topic == "loyalty.earn"
        assert directive.payload["order_ref"] == "ORD-001"

    @pytest.mark.django_db
    def test_earn_skips_zero_total(self):
        from shopman.services.loyalty import earn

        order = _make_order(total_q=0)

        earn(order)

        assert Directive.objects.count() == 0


# ══════════════════════════════════════════════════════════════════════
# services/fiscal.py
# ══════════════════════════════════════════════════════════════════════


class TestFiscalService:

    @pytest.mark.django_db
    @patch("shopman.services.fiscal.fiscal_pool")
    def test_emit_creates_directive(self, mock_pool):
        from shopman.services.fiscal import emit

        mock_pool.get_backend.return_value = MagicMock()

        item = _make_item()
        order = _make_order(data={}, items_list=[item])

        emit(order)

        directive = Directive.objects.last()
        assert directive is not None
        assert directive.topic == "fiscal.emit_nfce"

    @pytest.mark.django_db
    @patch("shopman.services.fiscal.fiscal_pool")
    def test_emit_noop_without_backend(self, mock_pool):
        from shopman.services.fiscal import emit

        mock_pool.get_backend.return_value = None

        order = _make_order()
        emit(order)

        assert Directive.objects.count() == 0

    @pytest.mark.django_db
    @patch("shopman.services.fiscal.fiscal_pool")
    def test_emit_idempotent(self, mock_pool):
        from shopman.services.fiscal import emit

        mock_pool.get_backend.return_value = MagicMock()

        order = _make_order(data={"nfce_access_key": "KEY123"})
        emit(order)

        assert Directive.objects.count() == 0

    @pytest.mark.django_db
    @patch("shopman.services.fiscal.fiscal_pool")
    def test_cancel_creates_directive(self, mock_pool):
        from shopman.services.fiscal import cancel

        mock_pool.get_backend.return_value = MagicMock()

        order = _make_order(data={"nfce_access_key": "KEY123"})
        cancel(order)

        directive = Directive.objects.last()
        assert directive is not None
        assert directive.topic == "fiscal.cancel_nfce"

    @pytest.mark.django_db
    @patch("shopman.services.fiscal.fiscal_pool")
    def test_cancel_noop_without_nfce(self, mock_pool):
        from shopman.services.fiscal import cancel

        mock_pool.get_backend.return_value = MagicMock()

        order = _make_order(data={})
        cancel(order)

        assert Directive.objects.count() == 0


# ══════════════════════════════════════════════════════════════════════
# services/cancellation.py
# ══════════════════════════════════════════════════════════════════════


class TestCancellationService:

    def test_cancel_transitions_status(self):
        from shopman.services.cancellation import cancel

        order = _make_order(status="confirmed")

        result = cancel(order, reason="customer_request", actor="customer")

        order.transition_status.assert_called_once()
        assert order.data["cancellation_reason"] == "customer_request"
        assert order.data["cancelled_by"] == "customer"
        assert result is True

    def test_cancel_skips_already_cancelled(self):
        from shopman.orderman.models import Order
        from shopman.services.cancellation import cancel

        order = _make_order(status=Order.Status.CANCELLED)

        result = cancel(order, reason="test")

        order.transition_status.assert_not_called()
        assert result is False

    def test_cancel_skips_completed(self):
        from shopman.orderman.models import Order
        from shopman.services.cancellation import cancel

        order = _make_order(status=Order.Status.COMPLETED)

        result = cancel(order, reason="test")

        order.transition_status.assert_not_called()
        assert result is False

    def test_cancel_merges_extra_data(self):
        from shopman.services.cancellation import cancel

        order = _make_order(status="confirmed", data={"foo": 1})

        cancel(
            order,
            reason="operator_reject",
            actor="operator:admin",
            extra_data={"rejected_by": "admin"},
        )

        assert order.data["cancellation_reason"] == "operator_reject"
        assert order.data["cancelled_by"] == "operator:admin"
        assert order.data["rejected_by"] == "admin"
        assert order.data["foo"] == 1


# ══════════════════════════════════════════════════════════════════════
# services/kds.py
# ══════════════════════════════════════════════════════════════════════


class TestKDSService:

    @patch("shopman.models.KDSTicket")
    @patch("shopman.models.KDSInstance")
    def test_dispatch_creates_tickets(self, mock_kds_inst, mock_ticket_cls):
        """Test that dispatch routes items to correct KDS instances."""
        from shopman.services.kds import dispatch

        # Setup: KDSTicket.objects.filter(...).exists() returns False (idempotent check)
        mock_ticket_cls.objects.filter.return_value.exists.return_value = False

        # No active instances → returns empty
        mock_kds_inst.objects.filter.return_value.exclude.return_value.prefetch_related.return_value = []

        order = _make_order()

        result = dispatch(order)
        assert result == []

    @pytest.mark.django_db
    def test_on_all_tickets_done_transitions_to_ready(self):
        from shopman.models import KDSInstance, KDSTicket
        from shopman.orderman.models import Order

        from shopman.models import Channel
        channel = Channel.objects.create(ref="kds-test", name="KDS Test")
        order = Order.objects.create(
            ref="KDS-ORD-001", channel_ref=channel.ref, status=Order.Status.PREPARING, total_q=1000,
        )
        inst = KDSInstance.objects.create(ref="prep-1", name="Prep", type="prep")
        KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="done")

        from shopman.services.kds import on_all_tickets_done

        result = on_all_tickets_done(order)

        order.refresh_from_db()
        assert result is True
        assert order.status == Order.Status.READY

    @pytest.mark.django_db
    def test_cancel_tickets_cancels_open_tickets(self):
        """cancel_tickets() sets status=cancelled on all open tickets."""
        from shopman.models import KDSInstance, KDSTicket
        from shopman.orderman.models import Order

        from shopman.models import Channel
        channel = Channel.objects.create(ref="kds-cancel-1", name="KDS Cancel 1")
        order = Order.objects.create(
            ref="KDS-CANCEL-001", channel_ref=channel.ref, status=Order.Status.PREPARING, total_q=1000,
        )
        inst = KDSInstance.objects.create(ref="prep-cancel-1", name="Prep Cancel", type="prep")
        t1 = KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="open")
        t2 = KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="open")

        from shopman.services.kds import cancel_tickets

        count = cancel_tickets(order)

        assert count == 2
        t1.refresh_from_db()
        t2.refresh_from_db()
        assert t1.status == "cancelled"
        assert t2.status == "cancelled"

    @pytest.mark.django_db
    def test_cancel_tickets_returns_zero_when_no_open_tickets(self):
        """cancel_tickets() returns 0 without error when no open tickets exist."""
        from shopman.models import KDSInstance, KDSTicket
        from shopman.orderman.models import Order

        from shopman.models import Channel
        channel = Channel.objects.create(ref="kds-cancel-2", name="KDS Cancel 2")
        order = Order.objects.create(
            ref="KDS-CANCEL-002", channel_ref=channel.ref, status=Order.Status.PREPARING, total_q=1000,
        )
        inst = KDSInstance.objects.create(ref="prep-cancel-2", name="Prep Cancel 2", type="prep")
        # Ticket already done — not "open"
        KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="done")

        from shopman.services.kds import cancel_tickets

        count = cancel_tickets(order)
        assert count == 0

    @pytest.mark.django_db
    def test_cancel_tickets_returns_zero_for_order_with_no_tickets(self):
        """cancel_tickets() is safe on orders with no tickets at all."""
        from shopman.orderman.models import Order

        from shopman.models import Channel
        channel = Channel.objects.create(ref="kds-cancel-3", name="KDS Cancel 3")
        order = Order.objects.create(
            ref="KDS-CANCEL-003", channel_ref=channel.ref, status=Order.Status.CONFIRMED, total_q=1000,
        )

        from shopman.services.kds import cancel_tickets

        count = cancel_tickets(order)
        assert count == 0

    @pytest.mark.django_db
    def test_on_all_tickets_done_noop_if_not_all_done(self):
        from shopman.models import KDSInstance, KDSTicket
        from shopman.orderman.models import Order

        from shopman.models import Channel
        channel = Channel.objects.create(ref="kds-test2", name="KDS Test 2")
        order = Order.objects.create(
            ref="KDS-ORD-002", channel_ref=channel.ref, status=Order.Status.PREPARING, total_q=1000,
        )
        inst = KDSInstance.objects.create(ref="prep-2", name="Prep 2", type="prep")
        KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="done")
        KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="pending")

        from shopman.services.kds import on_all_tickets_done

        result = on_all_tickets_done(order)

        assert result is False
        order.refresh_from_db()
        assert order.status == Order.Status.PREPARING


# ══════════════════════════════════════════════════════════════════════
# services/checkout.py
# ══════════════════════════════════════════════════════════════════════


class TestCheckoutService:

    @patch("shopman.services.checkout.Channel")
    @patch("shopman.services.checkout.ChannelConfig")
    @patch("shopman.services.checkout.CommitService")
    @patch("shopman.services.checkout.ModifyService")
    def test_process_applies_data_and_commits(self, mock_modify, mock_commit, mock_cfg, mock_channel):
        from shopman.config import ChannelConfig
        from shopman.services.checkout import process

        mock_cfg.for_channel.return_value = ChannelConfig()
        mock_commit.commit.return_value = {"order_ref": "ORD-001", "status": "committed"}

        result = process(
            session_key="sess-123",
            channel_ref="web",
            data={"fulfillment_type": "delivery", "customer": {"name": "João"}},
            idempotency_key="idem-123",
        )

        mock_modify.modify_session.assert_called_once()
        mock_commit.commit.assert_called_once()
        assert result["order_ref"] == "ORD-001"

    @patch("shopman.services.checkout.Channel")
    @patch("shopman.services.checkout.ChannelConfig")
    @patch("shopman.services.checkout.CommitService")
    @patch("shopman.services.checkout.ModifyService")
    def test_process_skips_modify_with_no_data(self, mock_modify, mock_commit, mock_cfg, mock_channel):
        from shopman.config import ChannelConfig
        from shopman.services.checkout import process

        mock_cfg.for_channel.return_value = ChannelConfig()
        mock_commit.commit.return_value = {"order_ref": "ORD-002", "status": "committed"}

        process(
            session_key="sess-456",
            channel_ref="web",
            data={},
            idempotency_key="idem-456",
        )

        mock_modify.modify_session.assert_not_called()
        mock_commit.commit.assert_called_once()


# ══════════════════════════════════════════════════════════════════════
# services/customer.py
# ══════════════════════════════════════════════════════════════════════


class TestCustomerService:

    @patch("shopman.services.customer._customers_available", return_value=False)
    def test_ensure_noop_without_customers_app(self, mock_avail):
        from shopman.services.customer import ensure

        order = _make_order()
        ensure(order)
        order.save.assert_not_called()

    @patch("shopman.services.customer._update_insights")
    @patch("shopman.services.customer._create_timeline_event")
    @patch("shopman.services.customer._save_delivery_address")
    @patch("shopman.services.customer.get_adapter")
    @patch("shopman.services.customer._customers_available", return_value=True)
    def test_ensure_phone_strategy(self, mock_avail, mock_get_adapter, mock_addr, mock_timeline, mock_insights):
        from shopman.services.customer import ensure

        customer = {"ref": "CLI-001", "first_name": "João", "last_name": "Silva", "phone": "+5543999999999"}
        adapter = MagicMock()
        adapter.get_customer_by_phone.return_value = customer
        mock_get_adapter.return_value = adapter

        order = _make_order(
            handle_ref="+5543999999999",
            snapshot={"data": {"customer": {"phone": "+5543999999999", "name": "João Silva"}}, "items": []},
        )

        ensure(order)

        assert order.data["customer_ref"] == "CLI-001"
        order.save.assert_called()

    @patch("shopman.services.customer._update_insights")
    @patch("shopman.services.customer._create_timeline_event")
    @patch("shopman.services.customer._save_delivery_address")
    @patch("shopman.services.customer._customers_available", return_value=True)
    def test_ensure_uses_registered_strategy(self, mock_avail, mock_addr, mock_timeline, mock_insights):
        """A strategy registered for a channel_ref is called instead of the default."""
        import shopman.services.customer as svc_module
        from shopman.services.customer import ensure, register_strategy

        customer = {"ref": "CUSTOM-001", "first_name": "", "last_name": "", "phone": ""}
        custom_fn = MagicMock(return_value=customer)

        original = svc_module._STRATEGIES.copy()
        try:
            register_strategy("test-channel", custom_fn)
            order = _make_order(channel_ref="test-channel")
            order.data = {}
            ensure(order)
            custom_fn.assert_called_once_with(order)
            assert order.data["customer_ref"] == "CUSTOM-001"
        finally:
            svc_module._STRATEGIES.clear()
            svc_module._STRATEGIES.update(original)

    @patch("shopman.services.customer._update_insights")
    @patch("shopman.services.customer._create_timeline_event")
    @patch("shopman.services.customer._save_delivery_address")
    @patch("shopman.services.customer.get_adapter")
    @patch("shopman.services.customer._customers_available", return_value=True)
    def test_ensure_falls_back_to_phone_when_no_strategy(
        self, mock_avail, mock_get_adapter, mock_addr, mock_timeline, mock_insights
    ):
        """Unrecognised channel with no registered strategy falls back to phone."""
        import shopman.services.customer as svc_module
        from shopman.services.customer import ensure

        customer = {"ref": "CLI-002", "first_name": "Ana", "last_name": "", "phone": "+5543888888888"}
        adapter = MagicMock()
        adapter.get_customer_by_phone.return_value = customer
        mock_get_adapter.return_value = adapter

        original = svc_module._STRATEGIES.copy()
        try:
            # Remove all strategies to simulate unregistered channel
            svc_module._STRATEGIES.clear()
            order = _make_order(
                channel_ref="unknown-channel",
                handle_ref="+5543888888888",
                snapshot={"data": {"customer": {"phone": "+5543888888888"}}, "items": []},
            )
            order.data = {}
            ensure(order)
            assert order.data["customer_ref"] == "CLI-002"
        finally:
            svc_module._STRATEGIES.clear()
            svc_module._STRATEGIES.update(original)


# ══════════════════════════════════════════════════════════════════════
# services/availability.py — bundle expansion (WP-CL2-1)
# ══════════════════════════════════════════════════════════════════════


class TestAvailabilityBundles:
    """availability.check() expands bundles and validates each component."""

    def _make_check_result(self, *, ok=True, available_qty=Decimal("100"), error_code=None, is_paused=False):
        return {
            "ok": ok,
            "available_qty": available_qty,
            "is_paused": is_paused,
            "is_planned": False,
            "breakdown": {},
            "error_code": error_code,
            "is_bundle": False,
            "failed_sku": None,
        }

    def test_bundle_all_components_available(self):
        """Bundle with all components available → ok=True, is_bundle=True, available_qty=min constructable."""
        from shopman.services import availability

        bundle_qty = Decimal("1")
        components = [
            {"sku": "FARINHA-001", "qty": Decimal("2")},
            {"sku": "MANTEIGA-001", "qty": Decimal("1")},
        ]

        # FARINHA has 50 units → 50/2=25 bundles
        # MANTEIGA has 200 units → 200/1=200 bundles
        # min = 25
        def fake_check(sku, qty, *, channel_ref=None):
            if sku == "FARINHA-001":
                return {**self._make_check_result(available_qty=Decimal("50")), "is_bundle": False, "failed_sku": None}
            return {**self._make_check_result(available_qty=Decimal("200")), "is_bundle": False, "failed_sku": None}

        with patch("shopman.services.availability.check", side_effect=fake_check):
            result = availability._check_bundle("BUNDLE-001", bundle_qty, components, channel_ref=None)

        assert result["ok"] is True
        assert result["is_bundle"] is True
        assert result["failed_sku"] is None
        assert result["available_qty"] == Decimal("25")

    def test_bundle_component_out_of_stock(self):
        """Bundle with 1 component insufficient stock → ok=False, failed_sku set."""
        from shopman.services import availability

        bundle_qty = Decimal("1")
        components = [
            {"sku": "FARINHA-001", "qty": Decimal("2")},
            {"sku": "MANTEIGA-001", "qty": Decimal("1")},
        ]

        def fake_check(sku, qty, *, channel_ref=None):
            if sku == "FARINHA-001":
                return {
                    "ok": False, "available_qty": Decimal("0"),
                    "is_paused": False, "is_planned": False,
                    "breakdown": {}, "error_code": "insufficient_stock",
                    "is_bundle": False, "failed_sku": None,
                }
            return {
                "ok": True, "available_qty": Decimal("200"),
                "is_paused": False, "is_planned": False,
                "breakdown": {}, "error_code": None,
                "is_bundle": False, "failed_sku": None,
            }

        with patch("shopman.services.availability.check", side_effect=fake_check):
            result = availability._check_bundle("BUNDLE-001", bundle_qty, components, channel_ref=None)

        assert result["ok"] is False
        assert result["is_bundle"] is True
        assert result["failed_sku"] == "FARINHA-001"
        assert result["error_code"] == "insufficient_stock"

    def test_bundle_component_not_in_listing(self):
        """Bundle with 1 component not in listing → ok=False, error_code=not_in_listing."""
        from shopman.services import availability

        bundle_qty = Decimal("1")
        components = [{"sku": "COMP-A", "qty": Decimal("1")}]

        def fake_check(sku, qty, *, channel_ref=None):
            return {
                "ok": False, "available_qty": Decimal("0"),
                "is_paused": False, "is_planned": False,
                "breakdown": {}, "error_code": "not_in_listing",
                "is_bundle": False, "failed_sku": None,
            }

        with patch("shopman.services.availability.check", side_effect=fake_check):
            result = availability._check_bundle("BUNDLE-001", bundle_qty, components, channel_ref="ifood")

        assert result["ok"] is False
        assert result["error_code"] == "not_in_listing"
        assert result["failed_sku"] == "COMP-A"

    def test_bundle_component_paused(self):
        """Bundle with 1 component paused → ok=False, error_code=paused."""
        from shopman.services import availability

        bundle_qty = Decimal("1")
        components = [{"sku": "COMP-A", "qty": Decimal("1")}]

        def fake_check(sku, qty, *, channel_ref=None):
            return {
                "ok": False, "available_qty": Decimal("0"),
                "is_paused": True, "is_planned": False,
                "breakdown": {}, "error_code": "paused",
                "is_bundle": False, "failed_sku": None,
            }

        with patch("shopman.services.availability.check", side_effect=fake_check):
            result = availability._check_bundle("BUNDLE-001", bundle_qty, components, channel_ref=None)

        assert result["ok"] is False
        assert result["error_code"] == "paused"
        assert result["failed_sku"] == "COMP-A"

    def test_simple_product_not_expanded(self):
        """Non-bundle SKU: _expand_if_bundle returns None, check proceeds normally."""
        from shopman.services.availability import _expand_if_bundle

        from shopman.offerman.exceptions import CatalogError
        with patch("shopman.adapters.catalog.expand_bundle", side_effect=CatalogError("NOT_A_BUNDLE", sku="PAO-001")):
            result = _expand_if_bundle("PAO-001", Decimal("1"))

        assert result is None

    def test_bundle_same_sku_guard(self):
        """If expand returns single element with same SKU, treat as simple product."""
        from shopman.services.availability import _expand_if_bundle

        with patch("shopman.adapters.catalog.expand_bundle", return_value=[{"sku": "PAO-001", "qty": Decimal("1")}]):
            result = _expand_if_bundle("PAO-001", Decimal("1"))

        assert result is None


class TestAvailabilityReserveBundles:
    """reserve() creates one hold per bundle component."""

    def _make_status_bundle_ok(self):
        return {
            "ok": True,
            "available_qty": Decimal("10"),
            "is_paused": False,
            "is_planned": False,
            "breakdown": {},
            "error_code": None,
            "is_bundle": True,
            "failed_sku": None,
        }

    @patch("shopman.services.availability.alternatives")
    @patch("shopman.services.availability.get_adapter")
    @patch("shopman.services.availability._expand_if_bundle")
    @patch("shopman.services.availability.check")
    def test_reserve_bundle_creates_one_hold_per_component(
        self, mock_check, mock_expand, mock_get_adapter, mock_alternatives
    ):
        """reserve(bundle) success → N holds created, all with reference=session_key."""
        from shopman.services.availability import reserve

        mock_check.return_value = self._make_status_bundle_ok()
        mock_expand.return_value = [
            {"sku": "COMP-A", "qty": Decimal("2")},
            {"sku": "COMP-B", "qty": Decimal("1")},
        ]

        adapter = MagicMock()
        adapter.create_hold.side_effect = [
            {"success": True, "hold_id": "hold:1"},
            {"success": True, "hold_id": "hold:2"},
        ]
        mock_get_adapter.return_value = adapter
        mock_alternatives.find.return_value = []

        result = reserve(
            "BUNDLE-001", Decimal("1"),
            session_key="sess-abc",
            channel_ref=None,
        )

        assert result["ok"] is True
        assert result["is_bundle"] is True
        assert result["hold_ids"] == ["hold:1", "hold:2"]
        assert adapter.create_hold.call_count == 2
        # Each hold uses session_key as reference
        for call in adapter.create_hold.call_args_list:
            assert call.kwargs["reference"] == "sess-abc"

    @patch("shopman.services.availability.alternatives")
    @patch("shopman.services.availability.get_adapter")
    @patch("shopman.services.availability._expand_if_bundle")
    @patch("shopman.services.availability.check")
    def test_reserve_bundle_failure_releases_created_holds(
        self, mock_check, mock_expand, mock_get_adapter, mock_alternatives
    ):
        """reserve(bundle) with mid-flight failure → no holds remain, alternatives populated."""
        from shopman.services.availability import reserve

        mock_check.return_value = self._make_status_bundle_ok()
        mock_expand.return_value = [
            {"sku": "COMP-A", "qty": Decimal("2")},
            {"sku": "COMP-B", "qty": Decimal("1")},
        ]

        adapter = MagicMock()
        adapter.create_hold.side_effect = [
            {"success": True, "hold_id": "hold:1"},
            {"success": False, "error_code": "insufficient_stock"},
        ]
        mock_get_adapter.return_value = adapter
        mock_alternatives.find.return_value = [{"sku": "ALT-001"}]

        result = reserve(
            "BUNDLE-001", Decimal("1"),
            session_key="sess-abc",
            channel_ref=None,
        )

        assert result["ok"] is False
        assert result["error_code"] == "insufficient_stock"
        # Rollback: released the hold already created
        adapter.release_holds.assert_called_once_with(["hold:1"])


# ══════════════════════════════════════════════════════════════════════
# Module-level sanity: no imports from channels/ or shop/
# ══════════════════════════════════════════════════════════════════════


class TestNoForbiddenImports:

    SERVICE_MODULES = [
        "shopman.services.stock",
        "shopman.services.payment",
        "shopman.services.customer",
        "shopman.services.notification",
        "shopman.services.fulfillment",
        "shopman.services.loyalty",
        "shopman.services.fiscal",
        "shopman.services.cancellation",
        "shopman.services.kds",
        "shopman.services.checkout",
    ]

    @pytest.mark.parametrize("module_path", SERVICE_MODULES)
    def test_no_channels_or_shop_imports(self, module_path):
        """Verify services don't import from channels/ or shop/."""
        import importlib
        import inspect

        mod = importlib.import_module(module_path)
        source = inspect.getsource(mod)

        assert "from channels." not in source, f"{module_path} imports from channels/"
        assert "from channels " not in source, f"{module_path} imports from channels"
        assert "import channels." not in source, f"{module_path} imports channels"
        assert "from shop." not in source, f"{module_path} imports from shop/"
        assert "from shop " not in source, f"{module_path} imports from shop"
        assert "import shop." not in source, f"{module_path} imports shop"
