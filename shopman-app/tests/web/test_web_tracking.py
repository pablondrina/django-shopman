"""Tests for storefront tracking views: OrderTrackingView, OrderStatusPartialView."""
from __future__ import annotations

import pytest
from django.test import Client
from django.utils import timezone
from shopman.ordering.models import Fulfillment

from channels.web.views._helpers import _carrier_tracking_url

pytestmark = pytest.mark.django_db


# ── _carrier_tracking_url helper ─────────────────────────────────────


class TestCarrierTrackingUrl:
    def test_correios(self):
        url = _carrier_tracking_url("correios", "BR123")
        assert url == "https://rastreamento.correios.com.br/?objetos=BR123"

    def test_jadlog(self):
        url = _carrier_tracking_url("jadlog", "JDL456")
        assert url == "https://www.jadlog.com.br/tracking?code=JDL456"

    def test_unknown_carrier_returns_none(self):
        assert _carrier_tracking_url("motoboy", "M001") is None

    def test_empty_carrier_returns_none(self):
        assert _carrier_tracking_url("", "BR123") is None

    def test_empty_code_returns_none(self):
        assert _carrier_tracking_url("correios", "") is None

    def test_case_insensitive(self):
        url = _carrier_tracking_url("Correios", "BR789")
        assert url == "https://rastreamento.correios.com.br/?objetos=BR789"


# ── OrderTrackingView ─────────────────────────────────────────────────


class TestOrderTrackingView:
    def test_tracking_page(self, client: Client, order):
        resp = client.get(f"/pedido/{order.ref}/")
        assert resp.status_code == 200
        assert b"ORD-001" in resp.content

    def test_tracking_not_found(self, client: Client):
        resp = client.get("/pedido/NOPE/")
        assert resp.status_code == 404

    def test_tracking_shows_status(self, client: Client, order):
        resp = client.get(f"/pedido/{order.ref}/")
        assert resp.status_code == 200
        assert b"Recebido" in resp.content

    def test_tracking_shows_total(self, client: Client, order):
        resp = client.get(f"/pedido/{order.ref}/")
        assert b"16,00" in resp.content

    def test_tracking_shows_items(self, client: Client, order_items):
        resp = client.get(f"/pedido/{order_items.ref}/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Francês" in content or "PAO-FRANCES" in content

    def test_tracking_confirmed_status(self, client: Client, order):
        order.transition_status("confirmed", actor="test")
        resp = client.get(f"/pedido/{order.ref}/")
        assert b"Confirmado" in resp.content

    def test_tracking_cancelled_status(self, client: Client, order):
        order.transition_status("cancelled", actor="test")
        resp = client.get(f"/pedido/{order.ref}/")
        assert b"Cancelado" in resp.content


# ── OrderStatusPartialView ────────────────────────────────────────────


class TestOrderStatusPartialView:
    def test_status_partial(self, client: Client, order):
        resp = client.get(f"/pedido/{order.ref}/status/")
        assert resp.status_code == 200

    def test_status_partial_not_found(self, client: Client):
        resp = client.get("/pedido/NOPE/status/")
        assert resp.status_code == 404

    def test_status_partial_after_transition(self, client: Client, order):
        order.transition_status("confirmed", actor="test")
        resp = client.get(f"/pedido/{order.ref}/status/")
        assert resp.status_code == 200
        assert b"Confirmado" in resp.content


# ── WP-P4: Fulfillment Tracking ──────────────────────────────────────


class TestFulfillmentTracking:
    def test_tracking_shows_delivery_carrier_and_code(self, client: Client, order):
        Fulfillment.objects.create(
            order=order,
            status="dispatched",
            carrier="correios",
            tracking_code="BR123456789",
            dispatched_at=timezone.now(),
        )
        resp = client.get(f"/pedido/{order.ref}/")
        content = resp.content.decode()
        assert "correios" in content
        assert "BR123456789" in content
        assert "Entrega" in content

    def test_tracking_shows_carrier_link(self, client: Client, order):
        Fulfillment.objects.create(
            order=order,
            status="dispatched",
            carrier="correios",
            tracking_code="BR999888777",
            dispatched_at=timezone.now(),
        )
        resp = client.get(f"/pedido/{order.ref}/")
        content = resp.content.decode()
        assert "rastreamento.correios.com.br" in content
        assert "BR999888777" in content

    def test_tracking_no_link_for_unknown_carrier(self, client: Client, order):
        Fulfillment.objects.create(
            order=order,
            status="dispatched",
            carrier="motoboy",
            tracking_code="MOTO-001",
            dispatched_at=timezone.now(),
        )
        resp = client.get(f"/pedido/{order.ref}/")
        content = resp.content.decode()
        assert "motoboy" in content
        assert "MOTO-001" in content
        assert "Rastrear entrega" not in content

    def test_tracking_pickup_shows_store_info(self, client: Client, order, shop_instance):
        shop_instance.formatted_address = "Rua das Flores 123 - Centro - Londrina"
        shop_instance.opening_hours = {
            "monday": {"open": "06:00", "close": "20:00"},
            "tuesday": {"open": "06:00", "close": "20:00"},
        }
        shop_instance.save()

        # Pickup fulfillment: no carrier, no tracking_code
        Fulfillment.objects.create(
            order=order,
            status="in_progress",
        )
        resp = client.get(f"/pedido/{order.ref}/")
        content = resp.content.decode()
        assert "Retirada na Loja" in content
        assert "Rua das Flores" in content

    def test_tracking_timeline_includes_shipped_event(self, client: Client, order):
        now = timezone.now()
        Fulfillment.objects.create(
            order=order,
            status="dispatched",
            carrier="correios",
            tracking_code="BR111222333",
            dispatched_at=now,
        )
        resp = client.get(f"/pedido/{order.ref}/")
        content = resp.content.decode()
        assert "Enviado" in content
