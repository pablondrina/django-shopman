"""Tests for WP-R7 — web views bridge, refactored checkout/tracking, API, webhooks."""

from __future__ import annotations

from django.urls import reverse

# ── URL resolution tests ────────────────────────────────────────────


class TestStorefrontURLs:
    """Key storefront URLs resolve correctly."""

    def test_home(self, db):
        assert reverse("storefront:home") == "/"


class TestHomeViewXFrame:
    """WP-S4: home permite iframe no admin (SAMEORIGIN), não DENY global."""

    def test_home_sends_xframe_sameorigin(self, client, db):
        resp = client.get("/")
        assert resp.status_code == 200
        assert resp.get("X-Frame-Options") == "SAMEORIGIN"

    def test_checkout(self, db):
        assert reverse("storefront:checkout") == "/checkout/"
        assert reverse("storefront:checkout_order_summary") == "/checkout/summary/"

    def test_order_cancel(self, db):
        assert reverse("storefront:order_cancel", kwargs={"ref": "ORD-001"}) == "/pedido/ORD-001/cancelar/"

    def test_cart(self, db):
        assert reverse("storefront:cart") == "/cart/"

    def test_cart_add(self, db):
        assert reverse("storefront:cart_add") == "/cart/add/"

    def test_order_payment(self, db):
        assert reverse("storefront:order_payment", kwargs={"ref": "ORD-001"}) == "/pedido/ORD-001/pagamento/"

    def test_order_tracking(self, db):
        assert reverse("storefront:order_tracking", kwargs={"ref": "ORD-001"}) == "/pedido/ORD-001/"

    def test_menu(self, db):
        assert reverse("storefront:menu") == "/menu/"

    def test_login(self, db):
        assert reverse("storefront:login") == "/login/"

    def test_account(self, db):
        assert reverse("storefront:account") == "/minha-conta/"

    def test_gestor_pedidos(self, db):
        assert reverse("storefront:gestor_pedidos") == "/pedidos/"

    def test_kds_index(self, db):
        assert reverse("storefront:kds_index") == "/kds/"

    def test_pos(self, db):
        assert reverse("storefront:pos") == "/gestao/pos/"


class TestWebhookURLs:
    """Webhook URLs resolve correctly."""

    def test_efi_pix(self, db):
        assert reverse("webhooks:efi-pix-webhook") == "/api/webhooks/efi/pix/"

    def test_stripe(self, db):
        assert reverse("webhooks:stripe-webhook") == "/api/webhooks/stripe/"


# ── View import tests ───────────────────────────────────────────────


class TestViewImports:
    """Refactored views are correctly imported via the bridge."""

    def test_checkout_view_is_refactored(self):
        from shopman.web.views import CheckoutView

        assert CheckoutView.__module__ == "shopman.web.views.checkout"

    def test_order_cancel_view_is_refactored(self):
        from shopman.web.views import OrderCancelView

        assert OrderCancelView.__module__ == "shopman.web.views.tracking"

    def test_other_views_from_shopman(self):
        from shopman.web.views import MenuView

        assert "shopman.web" in MenuView.__module__

    def test_tracking_view_from_shopman(self):
        from shopman.web.views import OrderTrackingView

        assert "shopman.web" in OrderTrackingView.__module__


# ── Webhook import tests ────────────────────────────────────────────


class TestWebhookImports:
    def test_efi_webhook_importable(self):
        from shopman.webhooks.efi import EfiPixWebhookView

        assert EfiPixWebhookView is not None

    def test_stripe_webhook_importable(self):
        from shopman.webhooks.stripe import StripeWebhookView

        assert StripeWebhookView is not None

    def test_efi_uses_flows_dispatch(self):
        """EFI webhook uses shopman.flows.dispatch, not channels.hooks."""
        import inspect

        from shopman.webhooks.efi import EfiPixWebhookView

        source = inspect.getsource(EfiPixWebhookView._process_order_payment)
        assert "dispatch(order" in source
        assert "on_payment_confirmed" not in source

    def test_stripe_uses_flows_dispatch(self):
        """Stripe webhook uses shopman.flows.dispatch, not channels.hooks."""
        import inspect

        from shopman.webhooks.stripe import StripeWebhookView

        source = inspect.getsource(StripeWebhookView._trigger_order_hooks)
        assert "dispatch(order" in source
        assert "on_payment_confirmed" not in source


# ── Checkout refactoring tests ──────────────────────────────────────


class TestCheckoutUsesService:
    """CheckoutView.post() delegates to services.checkout.process()."""

    def test_checkout_calls_service(self):
        import inspect

        from shopman.web.views.checkout import CheckoutView

        source = inspect.getsource(CheckoutView.post)
        assert "checkout_process(" in source
        # Must NOT call CommitService directly
        assert "CommitService.commit(" not in source


class TestOrderCancelUsesService:
    """OrderCancelView.post() delegates to services.cancellation.cancel()."""

    def test_cancel_calls_service(self):
        import inspect

        from shopman.web.views.tracking import OrderCancelView

        source = inspect.getsource(OrderCancelView.post)
        assert "cancel(order" in source
        # Must NOT call release_holds_for_order or create Directive directly
        assert "release_holds_for_order" not in source
        assert "Directive.objects.create" not in source


# ── Templatetags bridge ─────────────────────────────────────────────


class TestTemplatetagsBridge:
    def test_storefront_tags_loadable(self):
        from shopman.templatetags.storefront_tags import register

        assert register is not None

    def test_format_phone_filter(self):
        from shopman.templatetags.storefront_tags import format_phone

        assert format_phone("+5543999999999") == "(43) 99999-9999"

    def test_format_money_filter(self):
        from shopman.templatetags.storefront_tags import format_money

        assert format_money(1500) == "R$\u00a015,00"


# ── API bridge ──────────────────────────────────────────────────────


class TestAPIBridge:
    def test_api_urls_importable(self):
        from shopman.api.urls import urlpatterns

        assert len(urlpatterns) > 0

    def test_api_cart_url(self, db):
        url = reverse("api-cart")
        assert url == "/api/cart/"

    def test_api_checkout_url(self, db):
        url = reverse("api-checkout")
        assert url == "/api/checkout/"
