"""Tests for storefront tracking views: ReorderView."""
from __future__ import annotations

from unittest.mock import patch

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db


class TestReorderView:
    """ReorderView collects skipped items and surfaces them as session feedback."""

    def test_reorder_skips_oos_items_with_session_flag(
        self, client: Client, order_items, product, croissant,
    ):
        """Items that raise CartUnavailableError are collected and stored in session."""
        from shopman.shop.web.cart import CartUnavailableError

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

        with patch("shopman.shop.web.views.tracking.CartService.add_item", side_effect=raise_for_oos):
            resp = client.post(f"/meus-pedidos/{order_items.ref}/reorder/")

        assert resp.status_code == 302
        skipped = client.session.get("reorder_skipped")
        assert skipped is not None
        assert any("Croissant" in name for name in skipped)

    def test_reorder_no_session_flag_when_all_added(
        self, client: Client, order_items,
    ):
        """No skipped items → reorder_skipped not in session."""
        with patch("shopman.shop.web.views.tracking.CartService.add_item"):
            resp = client.post(f"/meus-pedidos/{order_items.ref}/reorder/")

        assert resp.status_code == 302
        assert client.session.get("reorder_skipped") is None

    def test_reorder_skipped_banner_shown_on_menu(
        self, client: Client, order_items, croissant,
    ):
        """After reorder with skips, the menu page renders the skipped banner."""
        from shopman.shop.web.cart import CartUnavailableError

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

        with patch("shopman.shop.web.views.tracking.CartService.add_item", side_effect=raise_for_oos):
            client.post(f"/meus-pedidos/{order_items.ref}/reorder/")

        # Follow redirect to menu — banner should appear
        resp = client.get("/menu/")
        assert resp.status_code == 200
        assert b"indispon" in resp.content
        # Session cleared after render
        assert client.session.get("reorder_skipped") is None
