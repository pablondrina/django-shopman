"""Tests for storefront tracking views: ReorderView."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.test import Client
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
