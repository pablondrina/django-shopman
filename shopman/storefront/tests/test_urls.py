"""Tests for storefront URL routing, view correctness, and API bridge."""

from __future__ import annotations

from django.urls import reverse


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
        assert reverse("backstage:gestor_pedidos") == "/gestor/pedidos/"

    def test_kds_index(self, db):
        assert reverse("backstage:kds_index") == "/gestor/kds/"

    def test_pos(self, db):
        assert reverse("backstage:pos") == "/gestor/pos/"


class TestViewImports:
    """Views are correctly importable from storefront."""

    def test_checkout_view_is_importable(self):
        from shopman.storefront.views import CheckoutView

        assert CheckoutView.__module__ == "shopman.storefront.views.checkout"

    def test_order_cancel_view_is_importable(self):
        from shopman.storefront.views import OrderCancelView

        assert OrderCancelView.__module__ == "shopman.storefront.views.tracking"

    def test_menu_view_from_storefront(self):
        from shopman.storefront.views import MenuView

        assert "shopman.storefront" in MenuView.__module__

    def test_tracking_view_from_storefront(self):
        from shopman.storefront.views import OrderTrackingView

        assert "shopman.storefront" in OrderTrackingView.__module__


class TestCheckoutUsesService:
    """CheckoutView.post() delegates to services.checkout.process()."""

    def test_checkout_calls_service(self):
        import inspect

        from shopman.storefront.views.checkout import CheckoutView

        source = inspect.getsource(CheckoutView.post)
        assert "checkout_process(" in source
        assert "CommitService.commit(" not in source


class TestOrderCancelUsesService:
    """OrderCancelView.post() delegates to services.cancellation.cancel()."""

    def test_cancel_calls_service(self):
        import inspect

        from shopman.storefront.views.tracking import OrderCancelView

        source = inspect.getsource(OrderCancelView.post)
        assert "cancel(order" in source
        assert "release_holds_for_order" not in source
        assert "Directive.objects.create" not in source


class TestTemplatetagsBridge:
    def test_storefront_tags_loadable(self):
        from shopman.shop.templatetags.storefront_tags import register

        assert register is not None

    def test_format_phone_filter(self):
        from shopman.shop.templatetags.storefront_tags import format_phone

        assert format_phone("+5543999999999") == "(43) 99999-9999"
        assert format_phone("+12025551234") == "+1 202-555-1234"

    def test_format_money_filter(self):
        from shopman.shop.templatetags.storefront_tags import format_money

        assert format_money(1500) == "R$\u00a015,00"


class TestAPIBridge:
    def test_api_urls_importable(self):
        from shopman.storefront.api.urls import urlpatterns

        assert len(urlpatterns) > 0

    def test_api_cart_url(self, db):
        url = reverse("api-cart")
        assert url == "/api/v1/cart/"

    def test_api_checkout_url(self, db):
        url = reverse("api-checkout")
        assert url == "/api/v1/checkout/"
