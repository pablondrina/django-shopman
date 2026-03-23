"""Tests for storefront payment views: PaymentView, PaymentStatusView, MockPaymentConfirmView."""
from __future__ import annotations

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


# ── PaymentView ───────────────────────────────────────────────────────


class TestPaymentView:
    def test_payment_page(self, client: Client, order_with_payment):
        resp = client.get(f"/pedido/{order_with_payment.ref}/pagamento/")
        assert resp.status_code == 200
        assert b"25,00" in resp.content

    def test_payment_page_not_found(self, client: Client):
        resp = client.get("/pedido/NOPE/pagamento/")
        assert resp.status_code == 404

    def test_payment_page_shows_pix_code(self, client: Client, order_with_payment):
        resp = client.get(f"/pedido/{order_with_payment.ref}/pagamento/")
        assert resp.status_code == 200


# ── PaymentStatusView ─────────────────────────────────────────────────


class TestPaymentStatusView:
    def test_status_pending(self, client: Client, order_with_payment):
        resp = client.get(f"/pedido/{order_with_payment.ref}/pagamento/status/")
        assert resp.status_code == 200

    def test_status_paid_redirects(self, client: Client, order_paid):
        resp = client.get(f"/pedido/{order_paid.ref}/pagamento/status/")
        assert resp.status_code == 200
        assert resp.headers.get("HX-Redirect") == f"/pedido/{order_paid.ref}/"

    def test_status_cancelled(self, client: Client, order_with_payment):
        order_with_payment.status = "cancelled"
        order_with_payment.save(update_fields=["status"])
        resp = client.get(f"/pedido/{order_with_payment.ref}/pagamento/status/")
        assert resp.status_code == 200

    def test_status_not_found(self, client: Client):
        resp = client.get("/pedido/NOPE/pagamento/status/")
        assert resp.status_code == 404


# ── MockPaymentConfirmView ────────────────────────────────────────────


class TestMockPaymentConfirmView:
    def test_mock_confirm(self, client: Client, order_with_payment):
        resp = client.post(f"/pedido/{order_with_payment.ref}/pagamento/mock-confirm/")
        assert resp.status_code == 302
        assert f"/pedido/{order_with_payment.ref}/" in resp.url

        order_with_payment.refresh_from_db()
        assert order_with_payment.data["payment"]["status"] == "captured"
        assert order_with_payment.status == "confirmed"

    def test_mock_confirm_already_paid(self, client: Client, order_paid):
        resp = client.post(f"/pedido/{order_paid.ref}/pagamento/mock-confirm/")
        assert resp.status_code == 302

    def test_mock_confirm_requires_post(self, client: Client, order_with_payment):
        resp = client.get(f"/pedido/{order_with_payment.ref}/pagamento/mock-confirm/")
        assert resp.status_code == 405

    def test_mock_confirm_not_found(self, client: Client):
        resp = client.post("/pedido/NOPE/pagamento/mock-confirm/")
        assert resp.status_code == 404
