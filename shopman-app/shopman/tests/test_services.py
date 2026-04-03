"""
Tests for shopman.services — each service testable in isolation.

Uses mocking for Core services and adapters to ensure isolation.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from shopman.ordering.models import Directive

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
    order.channel = channel

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
# services/stock.py
# ══════════════════════════════════════════════════════════════════════


class TestStockService:

    @patch("shopman.services.stock._get_product")
    @patch("shopman.services.stock.StockService")
    @patch("shopman.services.stock.CatalogService")
    def test_hold_simple_items(self, mock_catalog, mock_stock, mock_get_product):
        from shopman.services.stock import hold

        mock_catalog.expand.side_effect = Exception("NOT_A_BUNDLE")
        mock_get_product.return_value = MagicMock(sku="PAO-001")
        mock_stock.hold.return_value = "hold:1"

        order = _make_order(
            snapshot={"items": [{"sku": "PAO-001", "qty": "5"}], "data": {}},
        )

        hold(order)

        mock_stock.hold.assert_called_once()
        assert order.data["hold_ids"][0]["hold_id"] == "hold:1"
        order.save.assert_called()

    @patch("shopman.services.stock._get_product")
    @patch("shopman.services.stock.StockService")
    @patch("shopman.services.stock.CatalogService")
    def test_hold_expands_bundles(self, mock_catalog, mock_stock, mock_get_product):
        from shopman.services.stock import hold

        mock_catalog.expand.return_value = [
            {"sku": "COMP-A", "qty": Decimal("2")},
            {"sku": "COMP-B", "qty": Decimal("3")},
        ]
        mock_get_product.return_value = MagicMock()
        mock_stock.hold.return_value = "hold:1"

        order = _make_order(
            snapshot={"items": [{"sku": "BUNDLE-1", "qty": "1"}], "data": {}},
        )

        hold(order)

        assert mock_stock.hold.call_count == 2
        assert len(order.data["hold_ids"]) == 2

    @patch("shopman.services.stock.StockService")
    def test_fulfill_calls_stock_service(self, mock_stock):
        from shopman.services.stock import fulfill

        order = _make_order(data={
            "hold_ids": [
                {"hold_id": "hold:1", "sku": "PAO-001", "qty": 5},
                {"hold_id": "hold:2", "sku": "PAO-002", "qty": 3},
            ],
        })

        fulfill(order)

        assert mock_stock.fulfill.call_count == 2

    @patch("shopman.services.stock.StockService")
    def test_release_calls_stock_service(self, mock_stock):
        from shopman.services.stock import release

        order = _make_order(data={
            "hold_ids": [{"hold_id": "hold:1", "sku": "PAO-001", "qty": 5}],
        })

        release(order)

        mock_stock.release.assert_called_once_with("hold:1")

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
        from shopman.services.payment import initiate

        adapter = MagicMock()
        intent = MagicMock()
        intent.intent_id = "INT-001"
        intent.status = "pending"
        intent.metadata = {"qrcode": "QR123", "brcode": "PIX123"}
        intent.client_secret = None
        intent.expires_at = None
        adapter.create_intent.return_value = intent
        mock_get_adapter.return_value = adapter

        order = _make_order(data={"payment": {"method": "pix"}}, total_q=5000)

        initiate(order)

        adapter.create_intent.assert_called_once()
        assert order.data["payment"]["intent_id"] == "INT-001"
        assert order.data["payment"]["qr_code"] == "QR123"
        order.save.assert_called()

    @patch("shopman.services.payment.get_adapter")
    def test_initiate_card(self, mock_get_adapter):
        from shopman.services.payment import initiate

        adapter = MagicMock()
        intent = MagicMock()
        intent.intent_id = "INT-002"
        intent.status = "pending"
        intent.metadata = None
        intent.client_secret = "cs_test_123"
        intent.expires_at = None
        adapter.create_intent.return_value = intent
        mock_get_adapter.return_value = adapter

        order = _make_order(data={"payment": {"method": "card"}}, total_q=5000)

        initiate(order)

        assert order.data["payment"]["client_secret"] == "cs_test_123"

    def test_initiate_counter_noop(self):
        from shopman.services.payment import initiate

        order = _make_order(data={"payment": {"method": "counter"}})
        initiate(order)
        order.save.assert_not_called()

    def test_initiate_idempotent(self):
        from shopman.services.payment import initiate

        order = _make_order(data={"payment": {"method": "pix", "intent_id": "INT-EXISTING"}})
        initiate(order)
        order.save.assert_not_called()

    @patch("shopman.services.payment.get_adapter")
    def test_refund_smart_noop(self, mock_get_adapter):
        from shopman.services.payment import refund

        order = _make_order(data={})
        refund(order)
        mock_get_adapter.assert_not_called()

    @patch("shopman.services.payment.get_adapter")
    def test_refund_with_intent(self, mock_get_adapter):
        from shopman.services.payment import refund

        adapter = MagicMock()
        result = MagicMock()
        result.success = True
        adapter.refund.return_value = result
        mock_get_adapter.return_value = adapter

        order = _make_order(data={"payment": {"method": "pix", "intent_id": "INT-001", "status": "captured"}})

        refund(order)

        adapter.refund.assert_called_once()
        assert order.data["payment"]["status"] == "refunded"

    @patch("shopman.services.payment.get_adapter")
    def test_capture(self, mock_get_adapter):
        from shopman.services.payment import capture

        adapter = MagicMock()
        result = MagicMock()
        result.success = True
        result.transaction_id = "TXN-001"
        adapter.capture.return_value = result
        mock_get_adapter.return_value = adapter

        order = _make_order(data={"payment": {"method": "pix", "intent_id": "INT-001", "status": "authorized"}})

        capture(order)

        assert order.data["payment"]["status"] == "captured"


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
    @patch("shopman.services.fiscal.get_adapter")
    def test_emit_creates_directive(self, mock_get_adapter):
        from shopman.services.fiscal import emit

        mock_get_adapter.return_value = MagicMock()

        item = _make_item()
        order = _make_order(data={}, items_list=[item])

        emit(order)

        directive = Directive.objects.last()
        assert directive is not None
        assert directive.topic == "fiscal.emit"

    @pytest.mark.django_db
    @patch("shopman.services.fiscal.get_adapter")
    def test_emit_noop_without_adapter(self, mock_get_adapter):
        from shopman.services.fiscal import emit

        mock_get_adapter.return_value = None

        order = _make_order()
        emit(order)

        assert Directive.objects.count() == 0

    @pytest.mark.django_db
    @patch("shopman.services.fiscal.get_adapter")
    def test_emit_idempotent(self, mock_get_adapter):
        from shopman.services.fiscal import emit

        mock_get_adapter.return_value = MagicMock()

        order = _make_order(data={"nfce_access_key": "KEY123"})
        emit(order)

        assert Directive.objects.count() == 0

    @pytest.mark.django_db
    @patch("shopman.services.fiscal.get_adapter")
    def test_cancel_creates_directive(self, mock_get_adapter):
        from shopman.services.fiscal import cancel

        mock_get_adapter.return_value = MagicMock()

        order = _make_order(data={"nfce_access_key": "KEY123"})
        cancel(order)

        directive = Directive.objects.last()
        assert directive is not None
        assert directive.topic == "fiscal.cancel"

    @pytest.mark.django_db
    @patch("shopman.services.fiscal.get_adapter")
    def test_cancel_noop_without_nfce(self, mock_get_adapter):
        from shopman.services.fiscal import cancel

        mock_get_adapter.return_value = MagicMock()

        order = _make_order(data={})
        cancel(order)

        assert Directive.objects.count() == 0


# ══════════════════════════════════════════════════════════════════════
# services/pricing.py
# ══════════════════════════════════════════════════════════════════════


class TestPricingService:

    @patch("shopman.services.pricing.CatalogService")
    def test_resolve_delegates_to_catalog(self, mock_catalog):
        from shopman.services.pricing import resolve

        mock_catalog.price.return_value = 1500

        result = resolve("PAO-001", qty=5, channel="web")

        mock_catalog.price.assert_called_once_with("PAO-001", qty=Decimal("5"), channel="web")
        assert result == 1500


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
        from shopman.ordering.models import Order
        from shopman.services.cancellation import cancel

        order = _make_order(status=Order.Status.CANCELLED)

        result = cancel(order, reason="test")

        order.transition_status.assert_not_called()
        assert result is False

    def test_cancel_skips_completed(self):
        from shopman.ordering.models import Order
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
    @patch("shopman.offering.models.CollectionItem")
    @patch("shopman.services.kds._get_prep_skus")
    def test_dispatch_creates_tickets(self, mock_prep, mock_ci, mock_kds_inst, mock_ticket_cls):
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
        from shopman.ordering.models import Channel, Order

        channel = Channel.objects.create(ref="kds-test", name="KDS Test")
        order = Order.objects.create(
            ref="KDS-ORD-001", channel=channel, status=Order.Status.PROCESSING, total_q=1000,
        )
        inst = KDSInstance.objects.create(ref="prep-1", name="Prep", type="prep")
        KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="done")

        from shopman.services.kds import on_all_tickets_done

        result = on_all_tickets_done(order)

        order.refresh_from_db()
        assert result is True
        assert order.status == Order.Status.READY

    @pytest.mark.django_db
    def test_on_all_tickets_done_noop_if_not_all_done(self):
        from shopman.models import KDSInstance, KDSTicket
        from shopman.ordering.models import Channel, Order

        channel = Channel.objects.create(ref="kds-test2", name="KDS Test 2")
        order = Order.objects.create(
            ref="KDS-ORD-002", channel=channel, status=Order.Status.PROCESSING, total_q=1000,
        )
        inst = KDSInstance.objects.create(ref="prep-2", name="Prep 2", type="prep")
        KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="done")
        KDSTicket.objects.create(order=order, kds_instance=inst, items=[], status="pending")

        from shopman.services.kds import on_all_tickets_done

        result = on_all_tickets_done(order)

        assert result is False
        order.refresh_from_db()
        assert order.status == Order.Status.PROCESSING


# ══════════════════════════════════════════════════════════════════════
# services/checkout.py
# ══════════════════════════════════════════════════════════════════════


class TestCheckoutService:

    @patch("shopman.services.checkout.CommitService")
    @patch("shopman.services.checkout.ModifyService")
    def test_process_applies_data_and_commits(self, mock_modify, mock_commit):
        from shopman.services.checkout import process

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

    @patch("shopman.services.checkout.CommitService")
    @patch("shopman.services.checkout.ModifyService")
    def test_process_skips_modify_with_no_data(self, mock_modify, mock_commit):
        from shopman.services.checkout import process

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
    @patch("shopman.services.customer._get_customer_service")
    @patch("shopman.services.customer._customers_available", return_value=True)
    def test_ensure_phone_strategy(self, mock_avail, mock_svc_fn, mock_addr, mock_timeline, mock_insights):
        from shopman.services.customer import ensure

        svc = MagicMock()
        customer = MagicMock()
        customer.ref = "CLI-001"
        customer.first_name = "João"
        svc.get_by_phone.return_value = customer
        mock_svc_fn.return_value = svc

        order = _make_order(
            handle_ref="+5543999999999",
            snapshot={"data": {"customer": {"phone": "+5543999999999", "name": "João Silva"}}, "items": []},
        )

        ensure(order)

        assert order.data["customer_ref"] == "CLI-001"
        order.save.assert_called()


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
        "shopman.services.pricing",
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
