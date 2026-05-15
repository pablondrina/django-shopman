"""Tests for storefront tracking views: ReorderView."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.test import Client
from django.utils import timezone
from shopman.orderman.models import Session

from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
from shopman.storefront.tests.web.conftest import (
    _ensure_listing_item,
    _seed_stock_for_product_sku,
)

pytestmark = pytest.mark.django_db


def _open_cart_items(client: Client) -> list[dict]:
    session_key = client.session["cart_session_key"]
    session = Session.objects.get(
        session_key=session_key,
        channel_ref=STOREFRONT_CHANNEL_REF,
        state="open",
    )
    return session.items


class TestReorderView:
    """ReorderView collects skipped items and surfaces them as session feedback."""

    def test_reorder_skips_oos_items_with_session_flag(
        self, client: Client, order_items, product, croissant,
    ):
        """Items that raise CartUnavailableError are collected and stored in session."""
        from shopman.shop.services.cart import CartUnavailableError

        def raise_for_oos(request, sku, **kwargs):
            if sku == croissant.sku:
                raise CartUnavailableError(
                    sku=sku,
                    requested_qty=2,
                    available_qty=0,
                    is_paused=False,
                    substitutes=[],
                    error_code="insufficient_stock",
                )

        with patch("shopman.storefront.views.tracking.CartService.add_item", side_effect=raise_for_oos):
            resp = client.post(f"/meus-pedidos/{order_items.ref}/reorder/")

        assert resp.status_code == 302
        skipped = client.session.get("reorder_skipped")
        assert skipped is not None
        assert any("Croissant" in name for name in skipped)

    def test_reorder_no_session_flag_when_all_added(
        self, client: Client, order_items,
    ):
        """No skipped items → reorder_skipped not in session, but reorder_source is."""
        with patch("shopman.storefront.views.tracking.CartService.add_item"):
            resp = client.post(f"/meus-pedidos/{order_items.ref}/reorder/")

        assert resp.status_code == 302
        assert client.session.get("reorder_skipped") is None
        assert client.session.get("reorder_source") is True

    def test_reorder_htmx_uses_full_redirect_and_closes_shell_overlays(
        self, client: Client, order_items,
    ):
        """HTMX reorder must not swap the home body under an open drawer/menu."""
        with patch("shopman.storefront.views.tracking.CartService.add_item"):
            resp = client.post(
                f"/meus-pedidos/{order_items.ref}/reorder/",
                HTTP_HX_REQUEST="true",
            )

        assert resp.status_code == 204
        assert resp["HX-Redirect"] == "/cart/"
        triggers = json.loads(resp["HX-Trigger"])
        assert "close-mobile-menu" in triggers
        assert "close-cart-drawer" in triggers

    def test_reorder_with_existing_cart_requires_explicit_choice(
        self, cart_session: Client, order_items,
    ):
        """A non-empty cart must not be changed until the customer chooses a strategy."""
        with patch("shopman.storefront.views.tracking.CartService.add_item") as add_item:
            resp = cart_session.post(
                f"/meus-pedidos/{order_items.ref}/reorder/",
                HTTP_HX_REQUEST="true",
            )

        assert resp.status_code == 200
        html = resp.content.decode()
        assert "Seu carrinho já tem itens" in html
        assert 'name="reorder_mode" value="replace"' in html
        assert 'name="reorder_mode" value="add"' in html
        add_item.assert_not_called()
        assert cart_session.session.get("reorder_source") is None

    def test_reorder_add_mode_appends_to_existing_cart(
        self, cart_session: Client, order_items, channel, product, croissant,
    ):
        """Adding keeps current cart quantities and sums repeated SKUs."""
        _seed_stock_for_product_sku(croissant.sku)
        _ensure_listing_item(channel, croissant, price_q=800)

        resp = cart_session.post(
            f"/meus-pedidos/{order_items.ref}/reorder/",
            {"reorder_mode": "add"},
        )

        assert resp.status_code == 302
        qty_by_sku = {item["sku"]: int(item["qty"]) for item in _open_cart_items(cart_session)}
        assert qty_by_sku[product.sku] == 12
        assert qty_by_sku[croissant.sku] == 2

    def test_reorder_replace_mode_replaces_existing_cart(
        self, cart_session: Client, order_items, channel, product, croissant,
    ):
        """Replacing abandons the current cart before rebuilding it from the past order."""
        _seed_stock_for_product_sku(croissant.sku)
        _ensure_listing_item(channel, croissant, price_q=800)

        resp = cart_session.post(
            f"/meus-pedidos/{order_items.ref}/reorder/",
            {"reorder_mode": "replace"},
        )

        assert resp.status_code == 302
        qty_by_sku = {item["sku"]: int(item["qty"]) for item in _open_cart_items(cart_session)}
        assert qty_by_sku[product.sku] == 10
        assert qty_by_sku[croissant.sku] == 2

    def test_reorder_skipped_banner_shown_on_cart(
        self, client: Client, order_items, croissant,
    ):
        """After reorder with skips, the cart page renders the skipped banner."""
        from shopman.shop.services.cart import CartUnavailableError

        def raise_for_oos(request, sku, **kwargs):
            if sku == croissant.sku:
                raise CartUnavailableError(
                    sku=sku,
                    requested_qty=2,
                    available_qty=0,
                    is_paused=False,
                    substitutes=[],
                    error_code="insufficient_stock",
                )

        with patch("shopman.storefront.views.tracking.CartService.add_item", side_effect=raise_for_oos):
            client.post(f"/meus-pedidos/{order_items.ref}/reorder/")

        resp = client.get("/cart/")
        assert resp.status_code == 200
        assert b"indispon" in resp.content
        assert b"Ver outros pedidos" in resp.content
        # Session flags cleared after render
        assert client.session.get("reorder_skipped") is None
        assert client.session.get("reorder_source") is None

    def test_reorder_ver_outros_pedidos_link_shown_without_skips(
        self, client: Client, order_items,
    ):
        """Even with no skips, the cart shows the 'Ver outros pedidos' link."""
        with patch("shopman.storefront.views.tracking.CartService.add_item"):
            client.post(f"/meus-pedidos/{order_items.ref}/reorder/")

        resp = client.get("/cart/")
        assert resp.status_code == 200
        assert b"Ver outros pedidos" in resp.content


class TestTrackingApi:
    """Nuxt tracking API consumes the canonical order tracking projection."""

    def test_tracking_api_returns_full_customer_contract(
        self, client: Client, order_items,
    ):
        resp = client.get(f"/api/v1/tracking/{order_items.ref}/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ref"] == order_items.ref
        assert data["status"] == "new"
        assert data["is_active"] is True
        assert isinstance(data["can_cancel"], bool)
        assert data["promise"]["title"]
        assert isinstance(data["progress_steps"], list)
        assert data["items"][0]["sku"] == "PAO-FRANCES"
        assert "payment_pending" in data
        assert "payment_status" in data
        assert data["requires_payment_gate"] is False
        assert data["payment_gate_url"] is None

    def test_tracking_api_exposes_canonical_payment_gate_redirect(
        self, client: Client, order_with_payment,
    ):
        from shopman.orderman.models import Order

        order_with_payment.data["payment"]["expires_at"] = (
            timezone.now() + timezone.timedelta(minutes=10)
        ).isoformat()
        order_with_payment.save(update_fields=["data", "updated_at"])
        Order.objects.filter(pk=order_with_payment.pk).update(
            status="confirmed",
            updated_at=timezone.now(),
        )
        order_with_payment.refresh_from_db()

        resp = client.get(f"/api/v1/tracking/{order_with_payment.ref}/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["requires_payment_gate"] is True
        assert data["payment_gate_url"] == f"/pedido/{order_with_payment.ref}/pagamento"
        assert data["payment_pending"] is True

    def test_tracking_api_cancel_blocks_non_cancellable_paid_order(
        self, client: Client, order_paid,
    ):
        resp = client.post(f"/api/v1/orders/{order_paid.ref}/cancel/")

        assert resp.status_code == 409
        assert resp.json()["error_code"] == "order_not_cancellable"
        order_paid.refresh_from_db()
        assert order_paid.status == "confirmed"

    def test_tracking_api_cancel_returns_updated_projection(
        self, client: Client, order,
    ):
        resp = client.post(f"/api/v1/orders/{order.ref}/cancel/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["is_active"] is False
        assert data["can_cancel"] is False
        order.refresh_from_db()
        assert order.status == "cancelled"

    def test_reorder_api_returns_skipped_items_with_reasons(
        self, client: Client, order_items,
    ):
        with patch(
            "shopman.storefront.services.orders.add_reorder_items",
            return_value=["Croissant"],
        ):
            resp = client.post(f"/api/v1/orders/{order_items.ref}/reorder/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["skipped"] == ["Croissant"]
        assert data["skipped_items"] == [
            {
                "name": "Croissant",
                "reason": "Indisponível para recompra agora.",
            }
        ]
