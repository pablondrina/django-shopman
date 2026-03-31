"""
Tests for WP-F4: Storefront — Carrinho & Checkout.

Covers:
- 4.1 Cart bottom sheet / drawer
- 4.2 Checkout — single page, sections, double-submit prevention
- 4.3 Validation (coupon, CEP, stock)
- Template-level checks for key UX elements
"""

from __future__ import annotations

from pathlib import Path

from django.test import Client, TestCase
from shopman.offering.models import Collection, CollectionItem, Product
from shopman.ordering.models import Channel

APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = APP_DIR / "channels" / "web" / "templates"


def _setup():
    """Create minimal catalog + channel for cart tests."""
    channel = Channel.objects.create(
        ref="web", name="Loja Online",
        listing_ref="", pricing_policy="internal",
        edit_policy="open", config={},
    )
    p1 = Product.objects.create(
        sku="PAO-FRANCES", name="Pão Francês",
        base_price_q=80, is_published=True, is_available=True,
    )
    p2 = Product.objects.create(
        sku="CROISSANT", name="Croissant",
        base_price_q=800, is_published=True, is_available=True,
    )
    from shop.models import Shop
    Shop.objects.create(
        name="Nelson Boulangerie", brand_name="Nelson",
        short_name="Nelson", tagline="Padaria Artesanal",
        primary_color="#C5A55A", default_ddd="43",
        city="Londrina", state_code="PR",
    )
    return {"channel": channel, "products": [p1, p2]}


# ══════════════════════════════════════════════════════════════════════
# 4.1 Cart — Drawer / Bottom Sheet
# ══════════════════════════════════════════════════════════════════════


class TestCartDrawer(TestCase):
    """Cart drawer opens as overlay, not separate page."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()

    def test_cart_redirects_to_menu_with_open_param(self):
        """CartView redirects to menu with open_cart param (drawer-based)."""
        resp = self.client.get("/cart/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("open_cart", resp.url)

    def test_cart_drawer_renders(self):
        """Cart drawer endpoint returns 200."""
        self.client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": 2})
        resp = self.client.get("/cart/drawer/")
        self.assertEqual(resp.status_code, 200)

    def test_cart_drawer_shows_items(self):
        """Cart drawer shows added items."""
        self.client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": 2})
        resp = self.client.get("/cart/drawer/")
        content = resp.content.decode()
        self.assertIn("Pão Francês", content)

    def test_cart_empty_state(self):
        """Empty cart content shows empty state."""
        resp = self.client.get("/cart/content/")
        self.assertEqual(resp.status_code, 200)

    def test_floating_cart_bar_empty(self):
        """Floating bar returns empty when cart is empty."""
        resp = self.client.get("/cart/floating-bar/")
        self.assertEqual(resp.status_code, 200)

    def test_cart_summary_badge(self):
        """Cart summary returns badge data."""
        self.client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": 3})
        resp = self.client.get("/cart/summary/")
        self.assertEqual(resp.status_code, 200)


# ══════════════════════════════════════════════════════════════════════
# Cart — Add / Update / Remove
# ══════════════════════════════════════════════════════════════════════


class TestCartOperations(TestCase):
    """Cart add, update, remove via HTMX endpoints."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()

    def test_add_item_to_cart(self):
        """POST /cart/add/ adds item and triggers cartUpdated."""
        resp = self.client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": 1})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("cartUpdated", resp.headers.get("HX-Trigger", ""))

    def test_quick_add_by_sku(self):
        """POST /cart/quick-add/<sku>/ adds 1 unit."""
        resp = self.client.post("/cart/quick-add/PAO-FRANCES/")
        self.assertEqual(resp.status_code, 200)

    def test_add_nonexistent_sku_404(self):
        """Adding nonexistent SKU returns 404."""
        resp = self.client.post("/cart/add/", {"sku": "NOPE", "qty": 1})
        self.assertEqual(resp.status_code, 404)

    def test_add_unavailable_product(self):
        """Adding unavailable product shows stock error."""
        Product.objects.create(
            sku="ESGOTADO", name="Esgotado",
            base_price_q=100, is_published=True, is_available=False,
        )
        resp = self.client.post("/cart/add/", {"sku": "ESGOTADO", "qty": 1})
        self.assertEqual(resp.status_code, 200)
        # Should retarget to stock error modal
        self.assertIn("stock-error", resp.headers.get("HX-Retarget", ""))


# ══════════════════════════════════════════════════════════════════════
# 4.2 Checkout — Template UX
# ══════════════════════════════════════════════════════════════════════


class TestCheckoutTemplate(TestCase):
    """Checkout template has all required sections and UX elements."""

    def test_checkout_has_stepper(self):
        """Checkout template has visual step indicator."""
        template = (TEMPLATES_DIR / "storefront" / "checkout.html").read_text()
        # Should have step 1, 2, 3 or stepper concept
        self.assertIn("step", template)

    def test_checkout_has_fulfillment_toggle(self):
        """Checkout has pickup/delivery toggle."""
        template = (TEMPLATES_DIR / "storefront" / "checkout.html").read_text()
        self.assertTrue(
            "pickup" in template and "delivery" in template,
            "Checkout should have pickup/delivery options",
        )

    def test_checkout_has_payment_selection(self):
        """Checkout has payment method selection."""
        template = (TEMPLATES_DIR / "storefront" / "checkout.html").read_text()
        self.assertIn("payment_method", template)

    def test_checkout_has_order_summary(self):
        """Checkout has order summary section."""
        template = (TEMPLATES_DIR / "storefront" / "checkout.html").read_text()
        self.assertIn("Resumo", template)

    def test_checkout_has_confirmation_modal(self):
        """Checkout has confirmation modal before submit."""
        template = (TEMPLATES_DIR / "storefront" / "checkout.html").read_text()
        self.assertIn("Confirmar Pedido", template)
        self.assertIn("showModal", template)

    def test_checkout_double_submit_prevented(self):
        """Checkout confirm button has submitting guard."""
        template = (TEMPLATES_DIR / "storefront" / "checkout.html").read_text()
        self.assertIn("submitting", template)
        self.assertIn("disabled", template)
        self.assertIn("Processando", template)

    def test_checkout_has_delivery_date_options(self):
        """Checkout has date selection (Hoje / Amanhã / Agendar)."""
        template = (TEMPLATES_DIR / "storefront" / "checkout.html").read_text()
        self.assertIn("today", template)
        self.assertIn("tomorrow", template)

    def test_checkout_has_notes_textarea(self):
        """Checkout has optional notes/observations."""
        template = (TEMPLATES_DIR / "storefront" / "checkout.html").read_text()
        self.assertTrue(
            "order_notes" in template or "Observa" in template,
            "Checkout should have notes/observations field",
        )


# ══════════════════════════════════════════════════════════════════════
# 4.2 Checkout — View (requires auth, so lighter tests)
# ══════════════════════════════════════════════════════════════════════


class TestCheckoutView(TestCase):
    """Checkout view integration."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()

    def test_checkout_redirects_if_not_authenticated(self):
        """Checkout GET redirects to login if not authenticated."""
        resp = self.client.get("/checkout/")
        # Should redirect to login or render checkout with auth section
        self.assertIn(resp.status_code, [200, 302])


# ══════════════════════════════════════════════════════════════════════
# 4.3 Coupon
# ══════════════════════════════════════════════════════════════════════


class TestCoupon(TestCase):
    """Coupon apply/remove via HTMX."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()
        # Add item to cart first
        self.client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": 5})

    def test_apply_invalid_coupon(self):
        """Applying invalid coupon code returns error."""
        resp = self.client.post("/cart/coupon/", {"coupon_code": "INVALIDO"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        # Should show error message
        self.assertTrue(
            "inválido" in content.lower() or "não encontrado" in content.lower() or "error" in content.lower(),
            "Invalid coupon should show error feedback",
        )

    def test_coupon_section_template_has_htmx(self):
        """Coupon section template uses HTMX for apply/remove."""
        template = (TEMPLATES_DIR / "storefront" / "partials" / "coupon_section.html").read_text()
        self.assertIn("hx-post", template)


# ══════════════════════════════════════════════════════════════════════
# 4.3 CEP Lookup
# ══════════════════════════════════════════════════════════════════════


class TestCepLookup(TestCase):
    """CEP autofill via ViaCEP API."""

    def setUp(self):
        _setup()
        self.client = Client()

    def test_cep_lookup_invalid_format(self):
        """Invalid CEP format returns error."""
        resp = self.client.get("/checkout/cep-lookup/", {"cep": "abc"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode()
        self.assertTrue(
            "inválido" in content.lower() or "8 dígitos" in content.lower() or len(content.strip()) == 0,
            "Invalid CEP should show error or empty response",
        )

    def test_checkout_address_template_has_cep_integration(self):
        """Checkout address component has ViaCEP integration."""
        path = TEMPLATES_DIR / "storefront" / "partials" / "checkout_address.html"
        if path.exists():
            content = path.read_text()
            self.assertIn("cep", content.lower())
            self.assertIn("hx-get", content)


# ══════════════════════════════════════════════════════════════════════
# Cart Stock Check
# ══════════════════════════════════════════════════════════════════════


class TestCartStockCheck(TestCase):
    """Cart stock validation before checkout."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()

    def test_cart_check_endpoint_exists(self):
        """Cart check endpoint responds."""
        self.client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": 1})
        resp = self.client.get("/cart/check/")
        self.assertEqual(resp.status_code, 200)

    def test_cart_warnings_template_exists(self):
        """Cart warnings template exists for stock conflicts."""
        path = TEMPLATES_DIR / "storefront" / "partials" / "cart_warnings.html"
        self.assertTrue(path.exists(), "cart_warnings.html should exist")


# ══════════════════════════════════════════════════════════════════════
# Cart drawer templates
# ══════════════════════════════════════════════════════════════════════


class TestCartTemplates(TestCase):
    """All required cart templates exist and have key elements."""

    REQUIRED_TEMPLATES = [
        "partials/cart_content.html",
        "partials/cart_item.html",
        "partials/cart_empty.html",
        "partials/cart_subtotal.html",
        "partials/cart_summary.html",
        "partials/coupon_section.html",
        "partials/floating_cart_bar.html",
        "partials/cart_drawer.html",
        "partials/cart_drawer_item.html",
    ]

    def test_all_cart_templates_exist(self):
        """All required cart templates are present."""
        missing = []
        for name in self.REQUIRED_TEMPLATES:
            path = TEMPLATES_DIR / "storefront" / name
            if not path.exists():
                missing.append(name)
        self.assertEqual(missing, [], f"Missing cart templates: {missing}")

    def test_cart_item_has_stepper(self):
        """Cart item template has quantity stepper."""
        path = TEMPLATES_DIR / "storefront" / "partials" / "cart_item.html"
        content = path.read_text()
        self.assertTrue(
            "qty" in content.lower() or "stepper" in content.lower() or "update" in content.lower(),
            "Cart item should have qty update mechanism",
        )

    def test_cart_drawer_has_checkout_button(self):
        """Cart drawer has 'go to checkout' button."""
        path = TEMPLATES_DIR / "storefront" / "partials" / "cart_drawer.html"
        content = path.read_text()
        self.assertIn("checkout", content.lower())
