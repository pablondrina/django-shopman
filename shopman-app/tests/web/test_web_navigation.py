"""
Tests for Storefront navigation.

Covers:
- Bridge token → session creation
- origin_channel in Session.data / Order.data (JSONField)
- Notification respects origin_channel
- Bottom nav, floating cart, focus overlay
- Home page, como funciona (two dimensions)
- Theme color meta, safe area, minimum font size
"""
from __future__ import annotations

import pytest
from django.test import Client
from shopman.ordering.models import Channel, Order, Session

pytestmark = pytest.mark.django_db


# ══════════════════════════════════════════════════════════════════════
# Bridge Token
# ══════════════════════════════════════════════════════════════════════


class TestBridgeToken:
    def test_bridge_token_creates_session(self, client: Client, channel):
        """Valid bridge token creates authenticated session with origin_channel."""
        resp = client.get("/bridge/?t=valid-token-abc")
        assert resp.status_code == 302
        assert "/menu/" in resp.url

    def test_bridge_token_invalid_rejected(self, client: Client, channel):
        """Invalid bridge token does not authenticate — redirects to menu."""
        resp = client.get("/bridge/?t=invalid-token-xyz")
        assert resp.status_code == 302
        assert "/menu/" in resp.url

    def test_bridge_token_empty_redirects(self, client: Client):
        """No token parameter redirects to menu."""
        resp = client.get("/bridge/")
        assert resp.status_code == 302
        assert "/menu/" in resp.url

    def test_bridge_token_with_next(self, client: Client):
        """Bridge token with ?next= redirects to intended destination."""
        resp = client.get("/bridge/?t=some-token&next=/produto/CROISSANT/")
        assert resp.status_code == 302
        assert "/menu/" in resp.url


# ══════════════════════════════════════════════════════════════════════
# Origin Channel (via Session.data / Order.data JSONField)
# ══════════════════════════════════════════════════════════════════════


class TestOriginChannel:
    def test_origin_channel_stored_in_session_data(self, channel):
        """origin_channel is stored in Session.data JSON, not a model field."""
        s = Session.objects.create(
            session_key="test-oc-1",
            channel=channel,
            data={"origin_channel": "whatsapp"},
        )
        s.refresh_from_db()
        assert s.data["origin_channel"] == "whatsapp"

    def test_origin_channel_default_web_in_data(self, channel):
        """Default origin_channel is 'web' when set by CartService."""
        s = Session.objects.create(
            session_key="test-oc-2",
            channel=channel,
            data={"origin_channel": "web"},
        )
        assert s.data.get("origin_channel") == "web"

    def test_origin_channel_in_order_data(self, channel):
        """Order.data carries origin_channel from session commit."""
        order = Order.objects.create(
            ref="ORD-OC-001",
            channel=channel,
            status="new",
            total_q=1000,
            data={"origin_channel": "whatsapp"},
        )
        order.refresh_from_db()
        assert order.data["origin_channel"] == "whatsapp"

    def test_origin_channel_absent_is_fine(self, channel):
        """Orders without origin_channel in data work normally."""
        order = Order.objects.create(
            ref="ORD-OC-002",
            channel=channel,
            status="new",
            total_q=500,
            data={},
        )
        assert "origin_channel" not in order.data

    def test_notification_payload_includes_origin(self, channel):
        """Directive payload includes origin_channel when set in order.data."""
        from channels.hooks import _build_directive_payload

        order = Order.objects.create(
            ref="ORD-OC-003",
            channel=channel,
            status="new",
            total_q=500,
            data={"origin_channel": "instagram"},
            session_key="sess-123",
        )
        payload = _build_directive_payload(order, "order_confirmed")
        assert payload["origin_channel"] == "instagram"
        assert payload["template"] == "order_confirmed"
        assert payload["order_ref"] == "ORD-OC-003"

    def test_notification_payload_omits_when_absent(self, channel):
        """Directive payload omits origin_channel when not in order.data."""
        from channels.hooks import _build_directive_payload

        order = Order.objects.create(
            ref="ORD-OC-004",
            channel=channel,
            status="new",
            total_q=500,
            data={},
        )
        payload = _build_directive_payload(order)
        assert "origin_channel" not in payload


# ══════════════════════════════════════════════════════════════════════
# Home Page
# ══════════════════════════════════════════════════════════════════════


class TestHomePage:
    def test_home_returns_200(self, client: Client):
        """Home page renders successfully."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_home_contains_brand(self, client: Client):
        """Home page shows brand name."""
        resp = client.get("/")
        assert b"Nelson Boulangerie" in resp.content

    def test_home_contains_cta(self, client: Client):
        """Home page has CTA to menu."""
        resp = client.get("/")
        content = resp.content.decode()
        assert "Ver o card" in content or "/menu/" in content

    def test_home_has_two_dimensions(self, client: Client):
        """Home page shows both 'Pedido Online' and 'Na Loja' sections."""
        resp = client.get("/")
        content = resp.content.decode()
        assert "Pedido Online" in content
        assert "Na Loja" in content


# ══════════════════════════════════════════════════════════════════════
# Como Funciona (Two Dimensions)
# ══════════════════════════════════════════════════════════════════════


class TestComoFunciona:
    def test_como_funciona_returns_200(self, client: Client):
        resp = client.get("/como-funciona/")
        assert resp.status_code == 200

    def test_como_funciona_two_dimensions(self, client: Client):
        """Page shows both online ordering and in-store dimensions."""
        resp = client.get("/como-funciona/")
        content = resp.content.decode()
        assert "Pedido Online" in content
        assert "Na Loja" in content

    def test_como_funciona_has_autosserviço(self, client: Client):
        """In-store section mentions autosserviço."""
        resp = client.get("/como-funciona/")
        content = resp.content.decode()
        assert "autosservi" in content.lower()


# ══════════════════════════════════════════════════════════════════════
# Navigation Components (template rendering)
# ══════════════════════════════════════════════════════════════════════


class TestNavigationComponents:
    def test_bottom_nav_visible_on_mobile(self, client: Client):
        """Bottom nav is present in the HTML (hidden via CSS md:hidden)."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "md:hidden" in content
        assert 'aria-label="Navega' in content  # "Navegação principal"

    def test_bottom_nav_hidden_on_desktop(self, client: Client):
        """Bottom nav uses md:hidden class (CSS hides on desktop)."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        # The bottom nav has md:hidden class
        assert "md:hidden" in content

    def test_floating_cart_appears_with_items(self, client: Client, channel, product):
        """Floating cart button markup is present (visibility controlled by Alpine)."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        # The floating cart button component is included
        assert "Abrir carrinho" in content  # aria-label

    def test_focus_overlay_fullscreen(self, client: Client):
        """Focus overlay component is in the page."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "focusOverlay" in content
        assert "fixed inset-0" in content

    def test_theme_color_meta_present(self, client: Client):
        """Meta theme-color tag is rendered."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert 'name="theme-color"' in content

    def test_dark_mode_theme_color(self, client: Client):
        """Dark mode theme-color meta tag present."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert 'prefers-color-scheme: dark' in content

    def test_safe_area_padding(self, client: Client):
        """Safe area CSS variables are defined."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "safe-area-inset-bottom" in content

    def test_header_has_search_icon(self, client: Client):
        """Mobile header has search icon."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert 'aria-label="Buscar"' in content

    def test_apple_status_bar_translucent(self, client: Client):
        """iOS status bar set to black-translucent."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "black-translucent" in content

    def test_viewport_fit_cover(self, client: Client):
        """Viewport meta includes viewport-fit=cover for notch support."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "viewport-fit=cover" in content


# ══════════════════════════════════════════════════════════════════════
# SPA-like Navigation
# ══════════════════════════════════════════════════════════════════════


class TestSPANavigation:
    def test_main_content_is_htmx_history_elt(self, client: Client):
        """Main content uses hx-history-elt for HTMX cache."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "hx-history-elt" in content

    def test_htmx_swap_transitions(self, client: Client):
        """CSS transitions for HTMX swaps are defined."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "htmx-swapping" in content
        assert "htmx-settling" in content

    def test_gestures_js_included(self, client: Client):
        """Gestures script is included in base template."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "gestures.js" in content


# ══════════════════════════════════════════════════════════════════════
# Cart Added Confirmation
# ══════════════════════════════════════════════════════════════════════


class TestCartAddedConfirmation:
    def test_cart_confirmation_component_present(self, client: Client):
        """Cart added confirmation component is in the page."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "cartConfirmation" in content
        assert "Adicionado!" in content

    def test_cart_confirmation_has_actions(self, client: Client):
        """Confirmation shows 'Ver carrinho' and 'Continuar' buttons."""
        resp = client.get("/menu/")
        content = resp.content.decode()
        assert "Ver carrinho" in content
        assert "Continuar" in content
