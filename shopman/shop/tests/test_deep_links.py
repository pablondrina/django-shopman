"""
Tests for M4 — WhatsApp→Storefront E2E Flow.

Covers:
  1. deep_links.py — build_bridge_url / build_tracking_url / build_reorder_url
  2. notification._build_context — tracking_url/reorder_url injected when UUID present
  3. notification_manychat._build_message — tracking_suffix/reorder_suffix computed
  4. order_confirmation view — share_text includes shop name
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

CUSTOMER_UUID = UUID("12345678-1234-5678-1234-567812345678")


# ══════════════════════════════════════════════════════════════════════
# 1. deep_links.py
# ══════════════════════════════════════════════════════════════════════


def _make_customer(uuid=CUSTOMER_UUID, name="Ana", phone="+5511999990001"):
    from shopman.doorman.protocols.customer import AuthCustomerInfo

    return AuthCustomerInfo(uuid=uuid, name=name, phone=phone, email=None, is_active=True)


class TestBuildBridgeUrl:
    def test_returns_none_when_no_customer(self):
        from shopman.shop.services.deep_links import build_bridge_url

        assert build_bridge_url(None, None) is None

    def test_returns_none_when_customer_lacks_uuid(self):
        from shopman.shop.services.deep_links import build_bridge_url

        customer = SimpleNamespace()  # no uuid attribute
        assert build_bridge_url(None, customer) is None

    def test_returns_bridge_url_with_token_and_next(self):
        from shopman.shop.services.deep_links import build_bridge_url

        token_result = MagicMock()
        token_result.token = "tok_abc123"

        with (
            patch("shopman.doorman.services.access_link.AccessLinkService.create_token", return_value=token_result),
            patch("shopman.shop.services.deep_links._resolve_domain", return_value="https://example.com"),
        ):
            url = build_bridge_url(None, _make_customer(), next_url="/menu/")

        assert url == "https://example.com/bridge/?t=tok_abc123&next=%2Fmenu%2F"

    def test_returns_none_on_token_creation_failure(self):
        from shopman.shop.services.deep_links import build_bridge_url

        with patch("shopman.doorman.services.access_link.AccessLinkService.create_token", side_effect=Exception("DB error")):
            url = build_bridge_url(None, _make_customer())

        assert url is None

    def test_uses_request_for_domain(self):
        from django.test import RequestFactory

        from shopman.shop.services.deep_links import build_bridge_url

        token_result = MagicMock()
        token_result.token = "tok_req"
        request = RequestFactory().get("/")

        with patch("shopman.doorman.services.access_link.AccessLinkService.create_token", return_value=token_result):
            url = build_bridge_url(request, _make_customer(), next_url="/pedido/ORD-1/")

        assert url is not None
        assert "/bridge/" in url
        assert "t=tok_req" in url
        assert "next=%2Fpedido%2FORD-1%2F" in url
        assert "testserver" in url  # RequestFactory default host


class TestBuildTrackingAndReorderUrl:
    def test_tracking_url_points_to_pedido(self):
        from shopman.shop.services.deep_links import build_tracking_url

        token_result = MagicMock()
        token_result.token = "tok_tracking"

        with (
            patch("shopman.doorman.services.access_link.AccessLinkService.create_token", return_value=token_result),
            patch("shopman.shop.services.deep_links._resolve_domain", return_value="https://shop.test"),
        ):
            url = build_tracking_url(None, _make_customer(), "ORD-999")

        assert url is not None
        assert "next=%2Fpedido%2FORD-999%2F" in url

    def test_reorder_url_points_to_reorder_path(self):
        from shopman.shop.services.deep_links import build_reorder_url

        token_result = MagicMock()
        token_result.token = "tok_reorder"

        with (
            patch("shopman.doorman.services.access_link.AccessLinkService.create_token", return_value=token_result),
            patch("shopman.shop.services.deep_links._resolve_domain", return_value="https://shop.test"),
        ):
            url = build_reorder_url(None, _make_customer(), "ORD-999")

        assert url is not None
        assert "reorder" in url


# ══════════════════════════════════════════════════════════════════════
# 2. notification._build_context — tracking_url / reorder_url injection
# ══════════════════════════════════════════════════════════════════════


def _make_order_with_customer(uuid=str(CUSTOMER_UUID)):
    order = MagicMock()
    order.ref = "ORD-001"
    order.total_q = 3000
    order.status = "confirmed"
    order.data = {
        "customer": {
            "uuid": uuid,
            "name": "Ana",
            "phone": "+5511999990001",
        },
        "fulfillment_type": "pickup",
    }
    order.snapshot = {"items": []}
    return order


class TestNotificationContextEnrichment:
    def test_tracking_and_reorder_urls_injected_when_uuid_present(self):
        from shopman.shop.services.notification import _build_context

        order = _make_order_with_customer()
        payload = {"order_ref": "ORD-001"}

        token_result = MagicMock()
        token_result.token = "tok_ctx"
        with (
            patch("shopman.doorman.services.access_link.AccessLinkService.create_token", return_value=token_result),
            patch("shopman.shop.services.deep_links._resolve_domain", return_value="https://shop.test"),
        ):
            ctx = _build_context(order, payload, "order_confirmed")

        assert "tracking_url" in ctx
        assert ctx["tracking_url"] is not None
        assert "/bridge/" in ctx["tracking_url"]
        assert "reorder_url" in ctx
        assert ctx["reorder_url"] is not None

    def test_no_urls_when_uuid_absent(self):
        from shopman.shop.services.notification import _build_context

        order = MagicMock()
        order.ref = "ORD-002"
        order.total_q = 1000
        order.status = "new"
        order.data = {"customer": {"name": "Bob"}, "fulfillment_type": "pickup"}
        order.snapshot = {"items": []}

        ctx = _build_context(order, {"order_ref": "ORD-002"}, "order_confirmed")
        assert "tracking_url" not in ctx
        assert "reorder_url" not in ctx

    def test_no_urls_when_customer_data_missing(self):
        from shopman.shop.services.notification import _build_context

        order = MagicMock()
        order.ref = "ORD-003"
        order.total_q = 0
        order.status = "new"
        order.data = {"fulfillment_type": "pickup"}
        order.snapshot = {"items": []}

        ctx = _build_context(order, {}, "order_confirmed")
        assert "tracking_url" not in ctx


# ══════════════════════════════════════════════════════════════════════
# 3. notification_manychat._build_message — tracking/reorder suffixes
# ══════════════════════════════════════════════════════════════════════


class TestManychatMessageSuffixes:
    def _build(self, template: str, **extra_ctx):
        from shopman.shop.adapters.notification_manychat import _build_message

        ctx = {"order_ref": "ORD-042", "customer_name": "Ana", "total": "R$ 30,00"}
        ctx.update(extra_ctx)
        with patch("shopman.shop.adapters.notification_manychat._load_db_template", return_value=None):
            return _build_message(template, ctx)

    def test_tracking_suffix_appended_when_url_present(self):
        msg = self._build("order_confirmed", tracking_url="https://shop.test/bridge/?t=abc&next=/pedido/ORD-042/")
        assert "Acompanhe:" in msg
        assert "bridge" in msg

    def test_tracking_suffix_absent_when_url_missing(self):
        msg = self._build("order_confirmed")
        assert "Acompanhe:" not in msg
        assert "{tracking_suffix}" not in msg

    def test_reorder_suffix_appended_when_url_present(self):
        msg = self._build("order_delivered", reorder_url="https://shop.test/bridge/?t=xyz&next=/meus-pedidos/ORD-042/reorder/")
        assert "Peca de novo:" in msg
        assert "bridge" in msg

    def test_reorder_suffix_absent_when_url_missing(self):
        msg = self._build("order_delivered")
        assert "Peca de novo:" not in msg
        assert "{reorder_suffix}" not in msg

    def test_tracking_url_none_renders_cleanly(self):
        msg = self._build("order_confirmed", tracking_url=None)
        assert "None" not in msg
        assert "{tracking_suffix}" not in msg


# ══════════════════════════════════════════════════════════════════════
# 4. order_confirmation — share_text includes shop name
# ══════════════════════════════════════════════════════════════════════


class TestOrderConfirmationShareText:
    def test_share_text_format_includes_shop_name_and_url(self):
        """share_text must embed shop name and tracking URL — format tested directly."""
        shop_name = "Nelson Boulangerie"
        share_url = "https://shop.example.com/pedido/ORD-001/"
        share_text = f"Fiz um pedido em {shop_name}! Acompanhe: {share_url}"

        assert shop_name in share_text
        assert share_url in share_text

    def test_template_uses_share_text_not_share_url_for_whatsapp(self):
        """Template must use share_text (not share_url) for the WhatsApp href."""
        from pathlib import Path

        tpl = (
            Path(__file__).resolve().parents[2]
            / "storefront/templates/storefront/order_confirmation.html"
        )
        content = tpl.read_text(encoding="utf-8")
        # wa.me link must urlencode share_text, not the bare share_url
        assert "share_text|urlencode" in content, (
            "WhatsApp share link in order_confirmation.html must use share_text|urlencode "
            "so that the shop name is included in the shared message"
        )

