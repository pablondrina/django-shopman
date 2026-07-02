"""
Tests for M4 — WhatsApp→Storefront E2E lifecycle.

Covers:
  1. access_urls.py — build_access_url / build_tracking_access_url / build_reorder_access_url
  2. notification._build_context — tracking_url/reorder_url injected when UUID present
  3. notification_manychat._build_message — tracking_suffix/reorder_suffix computed
  4. order_confirmation view — share_text includes shop name
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import UUID

CUSTOMER_UUID = UUID("12345678-1234-5678-1234-567812345678")


# ══════════════════════════════════════════════════════════════════════
# 1. access_urls.py
# ══════════════════════════════════════════════════════════════════════


def _make_customer(uuid=CUSTOMER_UUID, name="Ana", phone="+5511999990001"):
    from shopman.doorman.protocols.customer import AuthCustomerInfo

    return AuthCustomerInfo(uuid=uuid, name=name, phone=phone, email=None, is_active=True)


class TestBuildAccessUrl:
    def test_returns_none_when_no_customer(self):
        from shopman.shop.services.access_urls import build_access_url

        assert build_access_url(None) is None

    def test_returns_none_when_customer_lacks_uuid(self):
        from shopman.shop.services.access_urls import build_access_url

        customer = SimpleNamespace()  # no uuid attribute
        assert build_access_url(customer) is None

    def test_returns_store_magic_link_with_token(self, settings):
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://nelson.com"
        from shopman.shop.services.access_urls import build_access_url

        token_result = MagicMock()
        token_result.token = "tok_abc123"

        with patch(
            "shopman.doorman.services.access_link.AccessLinkService.create_token",
            return_value=token_result,
        ):
            url = build_access_url(_make_customer(), metadata={"order_ref": "ORD-1"})

        # Aponta para a LOJA (Nuxt), não há `next` (destino vem da metadata server-side).
        assert url == "https://nelson.com/a?t=tok_abc123"

    def test_url_is_relative_when_base_unset(self, settings):
        settings.SHOPMAN_STOREFRONT_BASE_URL = ""
        from shopman.shop.services.access_urls import build_access_url

        token_result = MagicMock()
        token_result.token = "tok_rel"

        with patch(
            "shopman.doorman.services.access_link.AccessLinkService.create_token",
            return_value=token_result,
        ):
            url = build_access_url(_make_customer())

        assert url == "/a?t=tok_rel"

    def test_returns_none_on_token_creation_failure(self):
        from shopman.shop.services.access_urls import build_access_url

        with patch("shopman.doorman.services.access_link.AccessLinkService.create_token", side_effect=Exception("DB error")):
            url = build_access_url(_make_customer())

        assert url is None


class TestBuildTrackingAndReorderAccessUrl:
    def test_tracking_access_url_carries_order_metadata(self, settings):
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.access_urls import build_tracking_access_url

        token_result = MagicMock()
        token_result.token = "tok_tracking"

        with patch(
            "shopman.doorman.services.access_link.AccessLinkService.create_token",
            return_value=token_result,
        ) as create:
            url = build_tracking_access_url(_make_customer(), "ORD-999")

        assert url == "https://shop.test/a?t=tok_tracking"
        assert create.call_args.kwargs["metadata"] == {"order_ref": "ORD-999"}

    def test_payment_access_url_carries_payment_action(self, settings):
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.access_urls import build_payment_access_url

        token_result = MagicMock()
        token_result.token = "tok_pay"

        with patch(
            "shopman.doorman.services.access_link.AccessLinkService.create_token",
            return_value=token_result,
        ) as create:
            url = build_payment_access_url(_make_customer(), "ORD-999")

        assert url == "https://shop.test/a?t=tok_pay"
        assert create.call_args.kwargs["metadata"] == {"order_ref": "ORD-999", "action": "payment"}

    def test_reorder_access_url_carries_reorder_action(self, settings):
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.access_urls import build_reorder_access_url

        token_result = MagicMock()
        token_result.token = "tok_reorder"

        with patch(
            "shopman.doorman.services.access_link.AccessLinkService.create_token",
            return_value=token_result,
        ) as create:
            url = build_reorder_access_url(_make_customer(), "ORD-999")

        assert url == "https://shop.test/a?t=tok_reorder"
        assert create.call_args.kwargs["metadata"] == {"order_ref": "ORD-999", "action": "reorder"}


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
    def test_tracking_and_reorder_urls_injected_when_uuid_present(self, settings):
        settings.SHOPMAN_STOREFRONT_BASE_URL = "https://shop.test"
        from shopman.shop.services.notification import _build_context

        order = _make_order_with_customer()
        payload = {"order_ref": "ORD-001"}

        token_result = MagicMock()
        token_result.token = "tok_ctx"
        with patch(
            "shopman.doorman.services.access_link.AccessLinkService.create_token",
            return_value=token_result,
        ):
            ctx = _build_context(order, payload, "order_confirmed")

        assert "tracking_url" in ctx
        assert ctx["tracking_url"] == "https://shop.test/a?t=tok_ctx"
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
        with patch("shopman.shop.adapters._notification_templates.db_template", return_value=(None, None)):
            return _build_message(template, ctx)

    def test_tracking_suffix_appended_when_url_present(self):
        msg = self._build("order_confirmed", tracking_url="https://shop.test/a?t=abc")
        assert "Acompanhe:" in msg
        assert "/a?t=abc" in msg

    def test_tracking_suffix_absent_when_url_missing(self):
        msg = self._build("order_confirmed")
        assert "Acompanhe:" not in msg
        assert "{tracking_suffix}" not in msg

    def test_reorder_suffix_appended_when_url_present(self):
        msg = self._build("order_delivered", reorder_url="https://shop.test/a?t=xyz")
        assert "Peca de novo:" in msg
        assert "/a?t=xyz" in msg

    def test_reorder_suffix_absent_when_url_missing(self):
        msg = self._build("order_delivered")
        assert "Peca de novo:" not in msg
        assert "{reorder_suffix}" not in msg

    def test_tracking_url_none_renders_cleanly(self):
        msg = self._build("order_confirmed", tracking_url=None)
        assert "None" not in msg
        assert "{tracking_suffix}" not in msg
