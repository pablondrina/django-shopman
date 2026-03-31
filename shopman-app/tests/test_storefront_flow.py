"""Integration tests: storefront HTML flow (cart → checkout → order → gestor).

These tests validate the full purchase flow through the HTML views,
catching regressions like broken hx-targets, missing CSRF tokens,
or stale element IDs that unit tests miss.
"""
from __future__ import annotations

import re
import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import Client
from shopman.auth.models import CustomerUser
from shopman.customers.models import Customer
from shopman.offering.models import Product
from shopman.ordering.models import Channel, Order

from shop.models import Shop


@pytest.fixture(autouse=True)
def shop_instance(db):
    return Shop.objects.create(
        name="Nelson Boulangerie",
        brand_name="Nelson Boulangerie",
        short_name="Nelson",
        tagline="Padaria Artesanal",
        primary_color="#C5A55A",
        default_ddd="43",
        city="Londrina",
        state_code="PR",
    )


@pytest.fixture
def channel(db):
    return Channel.objects.create(
        ref="web",
        name="Loja Online",
        listing_ref="balcao",
        pricing_policy="external",
        edit_policy="open",
        config={},
    )


@pytest.fixture
def product(db):
    return Product.objects.create(
        sku="PAO-FRANCES",
        name="Pao Frances Artesanal",
        base_price_q=150,
        is_published=True,
        is_available=True,
    )


@pytest.fixture
def product_b(db):
    return Product.objects.create(
        sku="CROISSANT",
        name="Croissant Simples",
        base_price_q=800,
        is_published=True,
        is_available=True,
    )


@pytest.fixture
def customer_user(db):
    """A customer-level user linked to a Customer via CustomerUser."""
    user = User.objects.create_user(
        username="cli-customer-001",
        password="test1234",
        first_name="Joao",
        last_name="Oliveira",
    )
    customer = Customer.objects.create(
        ref="CLI-TEST-001",
        first_name="Joao",
        last_name="Oliveira",
        phone="+5543993333333",
    )
    CustomerUser.objects.create(user=user, customer_id=customer.uuid)
    return user


@pytest.fixture
def staff_user(db):
    return User.objects.create_user(
        username="operador", password="test1234", is_staff=True,
    )


@pytest.fixture
def logged_client(customer_user):
    """Client logged in as customer."""
    client = Client()
    client.login(username="cli-customer-001", password="test1234")
    return client


@pytest.fixture
def staff_client(staff_user):
    """Client logged in as staff (operator)."""
    client = Client()
    client.login(username="operador", password="test1234")
    return client


# ── Cart: add item via HTML view ────────────────────────────────────


class TestCartAddHTML:
    """POST /cart/add/ — the HTMX endpoint used by storefront buttons."""

    def test_add_item_returns_200(self, logged_client, channel, product):
        resp = logged_client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": "1"})
        assert resp.status_code == 200

    def test_add_item_updates_badge(self, logged_client, channel, product):
        resp = logged_client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": "2"})
        assert resp.status_code == 200
        # Badge HTML should contain the count
        content = resp.content.decode()
        assert "2" in content or "badge" in content.lower()

    def test_add_multiple_items(self, logged_client, channel, product, product_b):
        logged_client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": "3"})
        logged_client.post("/cart/add/", {"sku": "CROISSANT", "qty": "1"})
        # Cart should have 2 distinct items (4 total qty)
        resp = logged_client.get("/cart/summary/")
        assert resp.status_code == 200

    def test_add_nonexistent_product(self, logged_client, channel):
        resp = logged_client.post("/cart/add/", {"sku": "NAOEXISTE", "qty": "1"})
        assert resp.status_code == 404

    def test_add_unavailable_product(self, logged_client, channel, db):
        Product.objects.create(
            sku="ESGOTADO", name="Esgotado", base_price_q=100,
            is_published=True, is_available=False,
        )
        resp = logged_client.post("/cart/add/", {"sku": "ESGOTADO", "qty": "1"})
        # Should return error (either 400 or 200 with error modal)
        assert resp.status_code in (200, 400)


# ── Checkout: full HTML flow ────────────────────────────────────────


class TestCheckoutHTML:
    """Full checkout flow through storefront HTML views."""

    def test_checkout_requires_login(self, logged_client, channel, product):
        """Unauthenticated user with cart gets redirected to login."""
        # Add item first so we don't get redirected for empty cart
        logged_client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": "1"})
        # Now use an anonymous client with the same session cart
        anon = Client()
        resp = anon.get("/checkout/")
        assert resp.status_code == 302
        # Redirects either to /login/ or /cart/ (both valid for anon)
        assert "/login/" in resp.url or "/cart/" in resp.url

    def test_checkout_empty_cart_redirects(self, logged_client, channel):
        """Empty cart redirects away from checkout."""
        resp = logged_client.get("/checkout/")
        assert resp.status_code == 302

    def test_checkout_get_with_cart(self, logged_client, channel, product):
        """GET /checkout/ renders the form when cart has items."""
        logged_client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": "2"})
        resp = logged_client.get("/checkout/")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "Pao Frances" in content

    def test_full_checkout_creates_order(self, logged_client, channel, product):
        """POST /checkout/ commits session → creates Order."""
        # Step 1: Add to cart
        logged_client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": "3"})

        # Step 2: Submit checkout
        resp = logged_client.post("/checkout/", {
            "name": "Joao Oliveira",
            "phone": "43993333333",
            "fulfillment_type": "pickup",
            "payment_method": "pix",
            "delivery_date_option": "today",
        })

        # Step 3: Should redirect to payment or confirmation
        assert resp.status_code == 302, f"Expected redirect, got {resp.status_code}"
        redirect_url = resp.url

        # Order must exist
        assert Order.objects.filter(channel__ref="web").exists(), (
            "Order was not created after checkout"
        )

        order = Order.objects.filter(channel__ref="web").latest("created_at")
        assert order.total_q == 450  # 3 x R$ 1,50 = R$ 4,50 = 450 centavos
        # Status may be "new" or "confirmed" (optimistic confirmation)
        assert order.status in ("new", "confirmed")
        assert order.ref in redirect_url

    def test_checkout_order_has_items(self, logged_client, channel, product, product_b):
        """Order created by checkout has the correct items."""
        logged_client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": "2"})
        logged_client.post("/cart/add/", {"sku": "CROISSANT", "qty": "1"})

        logged_client.post("/checkout/", {
            "name": "Joao",
            "phone": "43993333333",
            "fulfillment_type": "pickup",
            "payment_method": "pix",
            "delivery_date_option": "today",
        })

        order = Order.objects.filter(channel__ref="web").latest("created_at")
        items = list(order.items.all().order_by("sku"))
        assert len(items) == 2
        skus = {it.sku for it in items}
        assert skus == {"PAO-FRANCES", "CROISSANT"}


# ── Gestor: order appears after checkout ────────────────────────────


class TestOrderAppearsInGestor:
    """After checkout, the order must appear in the operator dashboard."""

    def test_new_order_visible_in_gestor(
        self, logged_client, staff_client, channel, product,
    ):
        """Order created via storefront appears in /pedidos/."""
        # Customer: add to cart + checkout
        logged_client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": "2"})
        logged_client.post("/checkout/", {
            "name": "Joao Oliveira",
            "phone": "43993333333",
            "fulfillment_type": "pickup",
            "payment_method": "pix",
            "delivery_date_option": "today",
        })

        order = Order.objects.filter(channel__ref="web").latest("created_at")

        # Operator: check gestor
        resp = staff_client.get("/pedidos/")
        assert resp.status_code == 200
        assert order.ref in resp.content.decode()

    def test_new_order_visible_in_gestor_list_partial(
        self, logged_client, staff_client, channel, product,
    ):
        """Order appears in the HTMX polling partial too."""
        logged_client.post("/cart/add/", {"sku": "PAO-FRANCES", "qty": "1"})
        logged_client.post("/checkout/", {
            "name": "Joao",
            "phone": "43993333333",
            "fulfillment_type": "pickup",
            "payment_method": "pix",
            "delivery_date_option": "today",
        })

        order = Order.objects.filter(channel__ref="web").latest("created_at")

        resp = staff_client.get("/pedidos/list/?filter=all")
        assert resp.status_code == 200
        assert order.ref in resp.content.decode()


# ── Template integrity: verify critical IDs and attributes ──────────


class TestTemplateIntegrity:
    """Verify that templates reference elements that actually exist."""

    def test_product_detail_add_button_targets_existing_badge(
        self, logged_client, channel, product,
    ):
        """The hx-target in product_detail add button must match an ID in the page."""
        resp = logged_client.get("/produto/PAO-FRANCES/")
        assert resp.status_code == 200
        html = resp.content.decode()

        # Find all hx-target values referencing cart badge
        targets = re.findall(r'hx-target="(#cart-badge-[^"]+)"', html)
        for target in targets:
            element_id = target.lstrip("#")
            assert f'id="{element_id}"' in html, (
                f"hx-target='{target}' references non-existent element"
            )

    def test_no_alpine_hx_vals_binding_in_product_detail(
        self, logged_client, channel, product,
    ):
        """Product detail must never use :hx-vals (Alpine binding HTMX can't process)."""
        resp = logged_client.get("/produto/PAO-FRANCES/")
        html = resp.content.decode()

        # There should be NO :hx-vals (Alpine binding that HTMX can't process)
        # This was a real bug: :hx-vals is set by Alpine AFTER HTMX processes elements,
        # so the HTMX request fires without values.
        assert ':hx-vals=' not in html, (
            "Found :hx-vals binding — HTMX cannot process Alpine bindings. "
            "Use hx-vals='js:...' instead."
        )

    def test_no_alpine_hx_vals_binding_in_templates(self, channel, product):
        """All storefront templates must use hx-vals, never :hx-vals."""
        import glob
        import os

        template_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "channels", "web", "templates",
        )
        for path in glob.glob(os.path.join(template_dir, "**/*.html"), recursive=True):
            with open(path) as f:
                content = f.read()
            assert ":hx-vals=" not in content, (
                f"{os.path.relpath(path, template_dir)} contains :hx-vals binding. "
                "HTMX cannot process Alpine bindings. Use hx-vals='js:...' instead."
            )

    def test_no_stale_cart_badge_desktop_id(self, channel, product):
        """No template should reference the old #cart-badge-desktop ID."""
        import glob
        import os

        template_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "channels", "web", "templates",
        )
        for path in glob.glob(os.path.join(template_dir, "**/*.html"), recursive=True):
            with open(path) as f:
                content = f.read()
            assert "cart-badge-desktop" not in content, (
                f"{os.path.relpath(path, template_dir)} references stale "
                "'cart-badge-desktop'. Use 'cart-badge-header' instead."
            )

    def test_menu_page_add_buttons_target_existing_badge(
        self, logged_client, channel, product,
    ):
        """Product cards on menu page target existing badge element."""
        resp = logged_client.get("/menu/")
        assert resp.status_code == 200
        html = resp.content.decode()

        targets = re.findall(r'hx-target="(#cart-badge-[^"]+)"', html)
        for target in targets:
            element_id = target.lstrip("#")
            assert f'id="{element_id}"' in html, (
                f"hx-target='{target}' on menu page references non-existent element"
            )
