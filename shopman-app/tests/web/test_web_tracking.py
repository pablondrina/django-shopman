"""Tests for storefront tracking views: OrderTrackingView, OrderStatusPartialView."""
from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


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
