"""
Tests for WP-B6: Bundle expansion, bundle stock hold, fulfillment tracking.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.test import Client, TestCase
from shopman.offering.models import Product, ProductComponent
from shopman.ordering.models import Channel, Directive, Fulfillment, Order, OrderItem

from channels.handlers.stock import StockHoldHandler

pytestmark = pytest.mark.django_db


# ── Bundle expansion in ProductDetailView ────────────────────────────


class TestProductDetailBundleExpansion:
    """ProductDetailView shows bundle components when product is a bundle."""

    @pytest.fixture
    def _shop(self, db):
        from shop.models import Shop
        return Shop.objects.create(
            name="Test", brand_name="Test", short_name="T",
            tagline="Tag", primary_color="#C5A55A", 
            default_ddd="43", city="Londrina", state_code="PR",
        )

    @pytest.fixture
    def bundle(self, db):
        return Product.objects.create(
            sku="KIT-CAFE", name="Kit Café da Manhã",
            base_price_q=2500, is_published=True, is_available=True,
        )

    @pytest.fixture
    def croissant(self, db):
        return Product.objects.create(
            sku="CROISSANT", name="Croissant",
            base_price_q=800, is_published=True,
        )

    @pytest.fixture
    def baguete(self, db):
        return Product.objects.create(
            sku="BAGUETE", name="Baguete",
            base_price_q=600, is_published=True,
        )

    @pytest.fixture
    def bundle_with_components(self, bundle, croissant, baguete):
        ProductComponent.objects.create(parent=bundle, component=croissant, qty=2)
        ProductComponent.objects.create(parent=bundle, component=baguete, qty=1)
        return bundle

    def test_product_detail_shows_bundle_components(self, client: Client, _shop, bundle_with_components):
        resp = client.get(f"/produto/{bundle_with_components.sku}/")
        assert resp.status_code == 200
        assert b"Croissant" in resp.content
        assert b"Baguete" in resp.content
        # "Contém:" section header
        assert "Contém:".encode() in resp.content

    def test_product_detail_no_components_for_regular(self, client: Client, _shop, croissant):
        resp = client.get(f"/produto/{croissant.sku}/")
        assert resp.status_code == 200
        assert "Contém:".encode() not in resp.content


# ── Bundle stock hold reserves components ────────────────────────────


class TestBundleStockHold(TestCase):
    """StockHoldHandler expands bundles into components for stock reservation."""

    def setUp(self):
        self.bundle = Product.objects.create(
            sku="KIT-CAFE", name="Kit Café", base_price_q=2500,
            is_published=True, is_available=True,
        )
        self.comp_a = Product.objects.create(
            sku="CROISSANT", name="Croissant", base_price_q=800,
            is_published=True,
        )
        self.comp_b = Product.objects.create(
            sku="CAFE", name="Café", base_price_q=500,
            is_published=True,
        )
        ProductComponent.objects.create(parent=self.bundle, component=self.comp_a, qty=2)
        ProductComponent.objects.create(parent=self.bundle, component=self.comp_b, qty=1)

    def test_bundle_hold_reserves_components(self):
        """When holding a bundle, components are reserved instead."""
        backend = MagicMock()
        handler = StockHoldHandler(backend)

        items = [
            {"sku": "KIT-CAFE", "qty": 1, "line_id": "line-1"},
        ]
        result = handler._aggregate_items_by_sku(items)

        # Should have component SKUs, not the bundle SKU
        assert "KIT-CAFE" not in result
        assert "CROISSANT" in result
        assert "CAFE" in result
        # 2x Croissant per bundle * 1 bundle = 2
        assert result["CROISSANT"]["qty"] == Decimal("2")
        # 1x Café per bundle * 1 bundle = 1
        assert result["CAFE"]["qty"] == Decimal("1")

    def test_bundle_hold_multiple_quantities(self):
        """Multiple bundles correctly multiply component quantities."""
        backend = MagicMock()
        handler = StockHoldHandler(backend)

        items = [
            {"sku": "KIT-CAFE", "qty": 3, "line_id": "line-1"},
        ]
        result = handler._aggregate_items_by_sku(items)

        assert result["CROISSANT"]["qty"] == Decimal("6")  # 2 * 3
        assert result["CAFE"]["qty"] == Decimal("3")  # 1 * 3

    def test_bundle_and_regular_items_combined(self):
        """Bundle components aggregate with standalone items of same SKU."""
        backend = MagicMock()
        handler = StockHoldHandler(backend)

        items = [
            {"sku": "KIT-CAFE", "qty": 1, "line_id": "line-1"},
            {"sku": "CROISSANT", "qty": 5, "line_id": "line-2"},
        ]
        result = handler._aggregate_items_by_sku(items)

        # 2 from bundle + 5 standalone = 7
        assert result["CROISSANT"]["qty"] == Decimal("7")
        assert result["CAFE"]["qty"] == Decimal("1")

    def test_regular_product_not_expanded(self):
        """Non-bundle products are aggregated normally."""
        backend = MagicMock()
        handler = StockHoldHandler(backend)

        items = [
            {"sku": "CROISSANT", "qty": 3, "line_id": "line-1"},
        ]
        result = handler._aggregate_items_by_sku(items)

        assert "CROISSANT" in result
        assert result["CROISSANT"]["qty"] == Decimal("3")


# ── Stock alerts (integration — contrib.alerts is enabled) ────────────


class TestStockAlertEnabled(TestCase):
    """Verify stocking.contrib.alerts is wired up in INSTALLED_APPS."""

    def test_alerts_app_installed(self):
        from django.apps import apps
        assert apps.is_installed("shopman.stocking.contrib.alerts")

    def test_alert_signal_connected(self):
        """Move.post_save should have the alert handler connected."""
        from django.db.models.signals import post_save

        # Resolve weakrefs to find on_move_created handler
        names = []
        for receiver_tuple in post_save.receivers:
            ref = receiver_tuple[1]
            try:
                obj = ref()
                if obj:
                    names.append(getattr(obj, "__name__", ""))
            except TypeError:
                names.append(getattr(ref, "__name__", ""))
        assert "on_move_created" in names


# ── Fulfillment tracking in OrderTrackingView ────────────────────────


class TestFulfillmentTracking(TestCase):
    """OrderTrackingView shows fulfillment data."""

    def setUp(self):
        self.channel = Channel.objects.create(
            ref="web", name="Web", config={},
        )
        self.order = Order.objects.create(
            ref="ORD-FUL-001", channel=self.channel,
            status="dispatched", total_q=5000, data={},
        )
        OrderItem.objects.create(
            order=self.order, line_id="line-1", sku="PAO",
            name="Pão", qty=10, unit_price_q=80, line_total_q=800,
        )

    def test_tracking_view_shows_fulfillment_data(self):
        from django.utils import timezone
        Fulfillment.objects.create(
            order=self.order, status="dispatched",
            tracking_code="BR123456789",
            tracking_url="https://rastreamento.correios.com.br/app/index.php?objetos=BR123456789",
            carrier="correios",
            dispatched_at=timezone.now(),
        )

        client = Client()
        resp = client.get(f"/pedido/{self.order.ref}/")
        assert resp.status_code == 200
        assert b"BR123456789" in resp.content
        assert b"correios" in resp.content
        assert b"Rastrear entrega" in resp.content

    def test_tracking_view_no_fulfillment(self):
        """Page still works without any fulfillment records."""
        client = Client()
        resp = client.get(f"/pedido/{self.order.ref}/")
        assert resp.status_code == 200
        assert b"Entrega" not in resp.content

    def test_tracking_context_includes_fulfillments(self):
        from django.utils import timezone

        from channels.web.views.tracking import _build_tracking_context

        Fulfillment.objects.create(
            order=self.order, status="dispatched",
            tracking_code="BR999", carrier="jadlog",
            dispatched_at=timezone.now(),
        )
        ctx = _build_tracking_context(self.order)
        assert len(ctx["delivery_fulfillments"]) == 1
        assert ctx["delivery_fulfillments"][0]["tracking_code"] == "BR999"
        assert ctx["delivery_fulfillments"][0]["carrier"] == "jadlog"
        assert ctx["delivery_fulfillments"][0]["status_label"] == "Despachado"


# ── Fulfillment auto-sync (verify existing behavior) ────────────────


class TestFulfillmentAutoSync(TestCase):
    """Verify auto_sync_fulfillment works: fulfillment.dispatched → order.dispatched."""

    def setUp(self):
        self.channel = Channel.objects.create(
            ref="sync-ch", name="Sync Channel",
            config={
                "flow": {
                    "transitions": {
                        "new": ["confirmed", "cancelled"],
                        "confirmed": ["processing", "ready", "cancelled"],
                        "processing": ["ready", "cancelled"],
                        "ready": ["dispatched", "completed"],
                        "dispatched": ["delivered", "returned"],
                        "delivered": ["completed", "returned"],
                    },
                    "terminal_statuses": ["completed", "cancelled"],
                    "auto_sync_fulfillment": True,
                },
            },
        )

    def test_fulfillment_dispatched_syncs_order(self):
        from channels.handlers.fulfillment import FulfillmentUpdateHandler

        order = Order.objects.create(
            ref="ORD-SYNC-1", channel=self.channel,
            status="ready", total_q=1000, data={},
        )
        ful = Fulfillment.objects.create(order=order, status="in_progress")

        d = Directive.objects.bulk_create([Directive(
            topic="fulfillment.update",
            payload={
                "order_ref": order.ref,
                "fulfillment_id": ful.pk,
                "new_status": "dispatched",
            },
        )])[0]

        handler = FulfillmentUpdateHandler()
        handler.handle(message=d, ctx={})

        order.refresh_from_db()
        assert order.status == "dispatched"
