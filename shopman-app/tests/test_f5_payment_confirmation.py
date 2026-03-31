"""
Tests for WP-F5: Storefront — Pagamento & Confirmação.

Covers:
- 5.1 Payment page — PIX (QR code, copy-paste, countdown, polling)
- 5.2 Payment page — Card (Stripe Elements, submit)
- 5.3 Order confirmation page (celebration, share, collapsible summary)
- Payment status partial (waiting, expired, cancelled states)
- View logic (redirect when paid/cancelled, expiry detection)
- Template-level checks for key UX elements
"""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from django.test import Client, TestCase, override_settings
from django.utils import timezone
from shopman.offering.models import Product
from shopman.ordering.models import Channel, Order, Session
from shopman.utils.monetary import format_money

APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = APP_DIR / "channels" / "web" / "templates"


def _setup():
    """Create minimal data: channel, shop, product, order."""
    channel = Channel.objects.create(
        ref="web", name="Loja Online",
        listing_ref="", pricing_policy="internal",
        edit_policy="open", config={
            "flow": {
                "transitions": {
                    "new": ["confirmed", "cancelled"],
                    "confirmed": ["processing", "cancelled"],
                    "processing": ["ready", "cancelled"],
                    "ready": ["completed"],
                    "completed": [],
                    "cancelled": [],
                },
                "terminal_statuses": ["completed", "cancelled"],
            },
        },
    )
    from shop.models import Shop
    Shop.objects.create(
        name="Nelson Boulangerie", brand_name="Nelson",
        short_name="Nelson", tagline="Padaria Artesanal",
        primary_color="#C5A55A", default_ddd="43",
        city="Londrina", state_code="PR",
    )
    product = Product.objects.create(
        sku="CROISSANT", name="Croissant",
        base_price_q=800, is_published=True, is_available=True,
    )
    return {"channel": channel, "product": product}


def _make_order(channel, *, status="new", payment_data=None, total_q=800):
    """Create a test order with optional payment data."""
    session = Session.objects.create(
        session_key="test-session",
        channel=channel,
        state="committed",
        data={},
    )
    data = {}
    if payment_data:
        data["payment"] = payment_data
    order = Order.objects.create(
        ref="ORD-F5-TEST",
        session_key=session.session_key,
        channel=channel,
        status=status,
        total_q=total_q,
        data=data,
    )
    # Add an item
    order.items.create(
        sku="CROISSANT", name="Croissant",
        qty=1, unit_price_q=800, line_total_q=800,
    )
    return order


# ══════════════════════════════════════════════════════════════════════
# 5.1 Payment Page — PIX
# ══════════════════════════════════════════════════════════════════════


class TestPixPaymentPage(TestCase):
    """PIX payment page: QR code, copy-paste, countdown, polling."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()
        self.order = _make_order(
            self.data["channel"],
            payment_data={
                "method": "pix",
                "status": "pending",
                "intent_id": "intent-123",
                "qr_code": "data:image/png;base64,ABC123",
                "copy_paste": "00020126580014br.gov.bcb.pix0136test-key",
                "expires_at": (timezone.now() + timedelta(minutes=15)).isoformat(),
            },
        )

    def test_payment_page_renders(self):
        """Payment page returns 200 for pending order."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        self.assertEqual(resp.status_code, 200)

    def test_pix_qr_code_renders(self):
        """QR code image/element is present."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("QR Code PIX", content)

    def test_pix_copy_paste_renders(self):
        """Copy-paste code input is present with value."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("PIX Copia e Cola", content)
        self.assertIn("00020126580014br.gov.bcb.pix", content)

    def test_pix_copy_button_alpine(self):
        """Copy button uses Alpine @click (not onclick)."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("@click=\"copyPix()\"", content)
        self.assertNotIn("onclick=", content.lower().replace("@click", ""))

    def test_pix_countdown_timer(self):
        """Countdown timer element with data-expires is present."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("pixTimer(", content)
        self.assertIn("Expira em", content)

    def test_pix_timer_color_transitions(self):
        """Timer JS includes color transition logic (warning at 2min, error at 30s)."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("text-warning", content)
        self.assertIn("text-error", content)
        # Thresholds: 120s (2min) and 30s
        self.assertIn("120", content)
        self.assertIn("30", content)

    def test_pix_polling_htmx(self):
        """HTMX polling is configured with 5s interval."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("hx-trigger=\"every 5s\"", content)
        self.assertIn("/pagamento/status/", content)

    def test_pix_total_display_large(self):
        """Total is displayed prominently (32px)."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("R$ 8,00", content)
        self.assertIn("text-[32px]", content)

    def test_pix_manual_recheck_button(self):
        """Manual recheck button exists."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("verificar agora", content.lower())


# ══════════════════════════════════════════════════════════════════════
# Payment Page — Redirects
# ══════════════════════════════════════════════════════════════════════


class TestPaymentRedirects(TestCase):
    """Payment view redirects when order is already paid or cancelled."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()

    def test_redirects_when_already_paid(self):
        """If payment already captured, redirect to tracking."""
        order = _make_order(
            self.data["channel"],
            payment_data={"method": "pix", "status": "captured"},
        )
        resp = self.client.get(f"/pedido/{order.ref}/pagamento/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"/pedido/{order.ref}/", resp.url)

    def test_redirects_when_cancelled(self):
        """If order cancelled, redirect to tracking."""
        order = _make_order(
            self.data["channel"],
            status="cancelled",
            payment_data={"method": "pix", "status": "pending"},
        )
        resp = self.client.get(f"/pedido/{order.ref}/pagamento/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"/pedido/{order.ref}/", resp.url)


# ══════════════════════════════════════════════════════════════════════
# 5.2 Payment Page — Card
# ══════════════════════════════════════════════════════════════════════


class TestCardPaymentPage(TestCase):
    """Card payment page: Stripe Elements mount point."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()
        self.order = _make_order(
            self.data["channel"],
            payment_data={
                "method": "card",
                "status": "pending",
                "intent_id": "intent-card-456",
                "client_secret": "pi_test_secret_abc123",
            },
        )

    def test_card_page_renders(self):
        """Card payment page returns 200."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        self.assertEqual(resp.status_code, 200)

    def test_card_stripe_element_mount(self):
        """Stripe Payment Element mount point exists."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("stripe-payment-element", content)

    def test_card_submit_button(self):
        """Submit button shows total and uses Alpine."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("Pagar R$", content)
        self.assertIn("submitCard()", content)

    def test_card_stripe_js_loaded(self):
        """Stripe.js script is loaded for card method."""
        resp = self.client.get(f"/pedido/{self.order.ref}/pagamento/")
        content = resp.content.decode()
        self.assertIn("js.stripe.com", content)


# ══════════════════════════════════════════════════════════════════════
# Payment Status Partial
# ══════════════════════════════════════════════════════════════════════


class TestPaymentStatusPartial(TestCase):
    """HTMX partial for payment status polling."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()

    def test_status_waiting(self):
        """Pending payment shows 'Aguardando pagamento'."""
        order = _make_order(
            self.data["channel"],
            payment_data={"method": "pix", "status": "pending"},
        )
        resp = self.client.get(f"/pedido/{order.ref}/pagamento/status/")
        content = resp.content.decode()
        self.assertIn("Aguardando pagamento", content)

    def test_status_cancelled_order(self):
        """Cancelled order shows cancellation state."""
        order = _make_order(
            self.data["channel"],
            status="cancelled",
            payment_data={"method": "pix", "status": "pending"},
        )
        resp = self.client.get(f"/pedido/{order.ref}/pagamento/status/")
        content = resp.content.decode()
        self.assertIn("cancelado", content.lower())
        self.assertIn("Fazer novo pedido", content)

    def test_status_expired_pix(self):
        """Expired PIX shows expiry state."""
        expired_at = (timezone.now() - timedelta(minutes=5)).isoformat()
        order = _make_order(
            self.data["channel"],
            payment_data={
                "method": "pix",
                "status": "pending",
                "expires_at": expired_at,
            },
        )
        resp = self.client.get(f"/pedido/{order.ref}/pagamento/status/")
        content = resp.content.decode()
        self.assertIn("expirado", content.lower())

    def test_status_paid_redirects(self):
        """Captured payment triggers HX-Redirect."""
        order = _make_order(
            self.data["channel"],
            payment_data={"method": "pix", "status": "captured"},
        )
        resp = self.client.get(f"/pedido/{order.ref}/pagamento/status/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("HX-Redirect", resp.headers)
        self.assertIn(f"/pedido/{order.ref}/", resp["HX-Redirect"])


# ══════════════════════════════════════════════════════════════════════
# 5.3 Order Confirmation Page
# ══════════════════════════════════════════════════════════════════════


class TestOrderConfirmation(TestCase):
    """Confirmation page: celebration, ref, share, collapsible summary."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()
        self.order = _make_order(
            self.data["channel"],
            status="confirmed",
            payment_data={"method": "counter", "status": "captured"},
        )

    def test_confirmation_page_renders(self):
        """Confirmation page returns 200."""
        resp = self.client.get(f"/pedido/{self.order.ref}/confirmacao/")
        self.assertEqual(resp.status_code, 200)

    def test_confirmation_shows_ref(self):
        """Order ref is visible and copyable."""
        resp = self.client.get(f"/pedido/{self.order.ref}/confirmacao/")
        content = resp.content.decode()
        self.assertIn(self.order.ref, content)
        # Copyable (clipboard API)
        self.assertIn("clipboard.writeText", content)

    def test_confirmation_confetti_animation(self):
        """CSS confetti animation elements are present."""
        resp = self.client.get(f"/pedido/{self.order.ref}/confirmacao/")
        content = resp.content.decode()
        self.assertIn("confetti-container", content)
        self.assertIn("confetti-piece", content)
        self.assertIn("confetti-fall", content)

    def test_confirmation_share_link(self):
        """WhatsApp share link is present with order ref."""
        resp = self.client.get(f"/pedido/{self.order.ref}/confirmacao/")
        content = resp.content.decode()
        self.assertIn("wa.me", content)
        self.assertIn("Compartilhar", content)

    def test_confirmation_items_collapsible(self):
        """Order items summary uses Alpine x-collapse."""
        resp = self.client.get(f"/pedido/{self.order.ref}/confirmacao/")
        content = resp.content.decode()
        self.assertIn("x-collapse", content)
        self.assertIn("Resumo do Pedido", content)

    def test_confirmation_tracking_link(self):
        """'Acompanhar pedido' link points to tracking page."""
        resp = self.client.get(f"/pedido/{self.order.ref}/confirmacao/")
        content = resp.content.decode()
        self.assertIn("Acompanhar pedido", content)
        self.assertIn(f"/pedido/{self.order.ref}/", content)

    def test_confirmation_total_display(self):
        """Total is displayed."""
        resp = self.client.get(f"/pedido/{self.order.ref}/confirmacao/")
        content = resp.content.decode()
        self.assertIn("R$ 8,00", content)

    def test_confirmation_success_icon(self):
        """Check icon (SVG, not emoji) is present."""
        resp = self.client.get(f"/pedido/{self.order.ref}/confirmacao/")
        content = resp.content.decode()
        self.assertIn("text-success", content)
        # SVG check icon, not emoji
        self.assertIn("<svg", content)
        self.assertNotIn("✅", content)


# ══════════════════════════════════════════════════════════════════════
# Template-level checks — no broken Django comments
# ══════════════════════════════════════════════════════════════════════


class TestTemplateComments(TestCase):
    """Ensure no multi-line {# #} comments leak as visible text."""

    def test_no_multiline_comment_tags(self):
        """All component templates use single-line {# #} or {% comment %}."""
        components_dir = TEMPLATES_DIR / "components"
        if not components_dir.exists():
            self.skipTest("Components dir not found")

        broken = []
        for html_file in components_dir.glob("*.html"):
            lines = html_file.read_text().splitlines()
            for i, line in enumerate(lines, 1):
                # Line opens {# but doesn't close #} on same line
                if "{#" in line and "#}" not in line:
                    broken.append(f"{html_file.name}:{i}: {line.strip()}")

        self.assertEqual(broken, [], f"Multi-line {{# #}} comments found:\n" + "\n".join(broken))

    def test_no_wp_f2_references_in_templates(self):
        """WP-F2 references should not leak into template output."""
        storefront_dir = TEMPLATES_DIR / "storefront"
        components_dir = TEMPLATES_DIR / "components"

        for template_dir in (storefront_dir, components_dir):
            if not template_dir.exists():
                continue
            for html_file in template_dir.rglob("*.html"):
                content = html_file.read_text()
                self.assertNotIn(
                    "WP-F2",
                    content,
                    f"WP-F2 reference found in {html_file.name}",
                )


# ══════════════════════════════════════════════════════════════════════
# Mock Payment Confirmation (dev-only)
# ══════════════════════════════════════════════════════════════════════


@override_settings(DEBUG=True)
class TestMockPaymentConfirm(TestCase):
    """DEV: Mock payment confirmation endpoint."""

    def setUp(self):
        self.data = _setup()
        self.client = Client()

    def test_mock_confirm_transitions_order(self):
        """Mock confirm marks payment captured and transitions order."""
        order = _make_order(
            self.data["channel"],
            payment_data={
                "method": "pix",
                "status": "pending",
                "intent_id": None,  # No real intent — mock path
            },
        )
        resp = self.client.post(f"/pedido/{order.ref}/pagamento/mock-confirm/")
        self.assertEqual(resp.status_code, 302)

        order.refresh_from_db()
        self.assertEqual(order.data["payment"]["status"], "captured")
        self.assertEqual(order.status, "confirmed")

    def test_mock_confirm_already_paid(self):
        """Mock confirm on already-paid order redirects to tracking."""
        order = _make_order(
            self.data["channel"],
            payment_data={"method": "pix", "status": "captured"},
        )
        resp = self.client.post(f"/pedido/{order.ref}/pagamento/mock-confirm/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn(f"/pedido/{order.ref}/", resp.url)

    @override_settings(DEBUG=False)
    def test_mock_confirm_404_in_production(self):
        """Mock confirm returns 404 when DEBUG=False."""
        order = _make_order(
            self.data["channel"],
            payment_data={"method": "pix", "status": "pending"},
        )
        resp = self.client.post(f"/pedido/{order.ref}/pagamento/mock-confirm/")
        self.assertEqual(resp.status_code, 404)


# ══════════════════════════════════════════════════════════════════════
# Bottom Nav — no duplicate header issue
# ══════════════════════════════════════════════════════════════════════


class TestBottomNavNoHTMXPageLoads(TestCase):
    """Bottom nav links should not use hx-get for full page navigations."""

    def test_bottom_nav_no_hx_get(self):
        """Bottom nav tabs use regular links, not HTMX swaps (prevents double-header)."""
        bottom_nav = TEMPLATES_DIR / "components" / "_bottom_nav.html"
        if not bottom_nav.exists():
            self.skipTest("Bottom nav not found")

        content = bottom_nav.read_text()
        # Main page links should not have hx-get (they return full pages)
        # Only HTMX partials (like badge polling) should have hx-get
        lines = content.splitlines()
        for i, line in enumerate(lines, 1):
            if "hx-target=\"#main-content\"" in line:
                self.fail(
                    f"Line {i}: Bottom nav still has hx-target='#main-content' "
                    "which causes double headers when views return full pages."
                )
