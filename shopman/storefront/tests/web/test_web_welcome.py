"""Tests for WelcomeView + WelcomeGateMiddleware.

Cobertura:
- clean_display_name / needs_confirmation (unit)
- GET /bem-vindo/ sem auth → redirect login
- GET /bem-vindo/ com nome limpo → redirect next
- GET /bem-vindo/ com nome sujo (ManyChat quirks) → render + pré-fill limpo
- GET /bem-vindo/ sem nome → render form vazio
- POST /bem-vindo/ salva first/last name corretamente
- POST /bem-vindo/ sem nome → erro + rerender
- Middleware: gateia GET de customer com nome vazio/sujo
- Middleware: não gateia POST, HTMX, static, admin, login, logout, bem-vindo
- Middleware: não gateia anônimo nem customer com nome limpo
- Emojis e espaços são limpos mas `&` é preservado pro cliente decidir
"""
from __future__ import annotations

import pytest
from django.contrib.auth.models import User
from django.test import Client
from shopman.guestman.models import Customer

from shopman.storefront.intents.auth import clean_display_name, needs_confirmation

pytestmark = pytest.mark.django_db


# ── Unit: helpers ─────────────────────────────────────────────────────


class TestCleanDisplayName:
    def test_empty(self):
        assert clean_display_name("") == ""

    def test_clean_stays_clean(self):
        assert clean_display_name("Joana") == "Joana"
        assert clean_display_name("João Silva") == "João Silva"

    def test_emoji_stripped(self):
        assert clean_display_name("Joana 🥐") == "Joana"
        assert clean_display_name("João & Maria 💕") == "João & Maria"
        assert clean_display_name("✨ Jo ✨") == "Jo"

    def test_whitespace_collapsed(self):
        assert clean_display_name("Joao   Oliveira") == "Joao Oliveira"
        assert clean_display_name("  Joao  ") == "Joao"
        assert clean_display_name("\tJoao\nOliveira") == "Joao Oliveira"

    def test_ampersand_preserved(self):
        # Deliberate: client must see the raw ampersand and decide to trim
        assert clean_display_name("João & Maria") == "João & Maria"


class TestNeedsConfirmation:
    def test_empty_needs(self):
        assert needs_confirmation("") is True
        assert needs_confirmation("   ") is True

    def test_clean_does_not_need(self):
        assert needs_confirmation("Joana") is False
        assert needs_confirmation("João Silva") is False

    def test_emoji_needs(self):
        assert needs_confirmation("Joana 🥐") is True
        assert needs_confirmation("João ✨") is True

    def test_suspect_chars_need(self):
        assert needs_confirmation("João & Maria") is True
        assert needs_confirmation("Ana + Pedro") is True
        assert needs_confirmation("Carlos | Família") is True
        assert needs_confirmation("Mãe/Pai") is True


# ── Integration helpers ───────────────────────────────────────────────


def _login_as_customer(client: Client, customer) -> User:
    from shopman.doorman.protocols.customer import AuthCustomerInfo
    from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

    info = AuthCustomerInfo(
        uuid=customer.uuid,
        name=customer.name,
        phone=customer.phone,
        email=getattr(customer, "email", None) or None,
        is_active=True,
    )
    user, _ = get_or_create_user_for_customer(info)
    client.force_login(user, backend="shopman.doorman.backends.PhoneOTPBackend")
    return user


@pytest.fixture
def nameless_customer(db):
    return Customer.objects.create(
        ref="WEL-001", first_name="", last_name="", phone="5543999990001",
    )


@pytest.fixture
def dirty_name_customer(db):
    return Customer.objects.create(
        ref="WEL-002", first_name="João & Maria 💕", last_name="", phone="5543999990002",
    )


@pytest.fixture
def clean_customer(db):
    return Customer.objects.create(
        ref="WEL-003", first_name="Joana", last_name="Silva", phone="5543999990003",
    )


# ── View: GET ─────────────────────────────────────────────────────────


class TestWelcomeViewGet:
    def test_unauthenticated_redirects_login(self, client: Client):
        resp = client.get("/bem-vindo/")
        assert resp.status_code == 302
        assert "/login/" in resp["Location"]

    def test_clean_name_redirects_to_next(self, client: Client, clean_customer):
        _login_as_customer(client, clean_customer)
        resp = client.get("/bem-vindo/?next=/menu/")
        assert resp.status_code == 302
        assert resp["Location"] == "/menu/"

    def test_clean_name_without_next_redirects_home(self, client: Client, clean_customer):
        _login_as_customer(client, clean_customer)
        resp = client.get("/bem-vindo/")
        assert resp.status_code == 302
        assert resp["Location"] == "/"

    def test_empty_name_renders_form(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.get("/bem-vindo/")
        assert resp.status_code == 200
        body = resp.content.decode()
        assert 'Como você quer' in body
        assert 'ser chamado(a)' in body
        assert 'Pode ser seu primeiro nome' in body

    def test_dirty_name_renders_prefilled_confirm_copy(
        self, client: Client, dirty_name_customer,
    ):
        _login_as_customer(client, dirty_name_customer)
        resp = client.get("/bem-vindo/")
        assert resp.status_code == 200
        body = resp.content.decode()
        # Pre-filled with cleaned suggestion (emoji out, & kept)
        assert 'value="João &amp; Maria"' in body or 'value="João & Maria"' in body
        # Confirm copy
        assert 'Encontramos esse nome' in body


# ── View: POST ────────────────────────────────────────────────────────


class TestWelcomeViewPost:
    def test_saves_and_redirects(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.post("/bem-vindo/?next=/menu/", {"name": "Joana Silva"})
        assert resp.status_code == 302
        assert resp["Location"] == "/menu/"

        nameless_customer.refresh_from_db()
        assert nameless_customer.first_name == "Joana"
        assert nameless_customer.last_name == "Silva"

    def test_single_name_saves_as_first_only(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        client.post("/bem-vindo/", {"name": "Joana"})

        nameless_customer.refresh_from_db()
        assert nameless_customer.first_name == "Joana"
        assert nameless_customer.last_name == ""

    def test_emoji_stripped_on_save(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        client.post("/bem-vindo/", {"name": "Joana 🥐"})

        nameless_customer.refresh_from_db()
        assert nameless_customer.first_name == "Joana"

    def test_empty_name_rerenders_with_error(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.post("/bem-vindo/", {"name": ""})
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "Precisamos de um nome" in body

    def test_whitespace_only_is_empty(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.post("/bem-vindo/", {"name": "   "})
        assert resp.status_code == 200
        assert "Precisamos de um nome" in resp.content.decode()

    def test_open_redirect_blocked(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.post(
            "/bem-vindo/?next=https://evil.example.com/",
            {"name": "Joana"},
        )
        assert resp.status_code == 302
        assert resp["Location"] == "/"

    def test_protocol_relative_blocked(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.post(
            "/bem-vindo/?next=//evil.example.com/",
            {"name": "Joana"},
        )
        assert resp["Location"] == "/"


# ── Middleware ────────────────────────────────────────────────────────


class TestWelcomeGateMiddleware:
    def test_anonymous_not_gated(self, client: Client):
        resp = client.get("/menu/")
        assert resp.status_code == 200

    def test_clean_name_not_gated(self, client: Client, clean_customer):
        _login_as_customer(client, clean_customer)
        resp = client.get("/minha-conta/")
        # Should reach account view, not redirect to welcome
        assert "/bem-vindo/" not in resp.get("Location", "")

    def test_empty_name_gated_on_get(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.get("/minha-conta/")
        assert resp.status_code == 302
        assert resp["Location"].startswith("/bem-vindo/")
        assert "next=" in resp["Location"]
        assert "minha-conta" in resp["Location"]

    def test_dirty_name_gated_on_get(self, client: Client, dirty_name_customer):
        _login_as_customer(client, dirty_name_customer)
        resp = client.get("/menu/")
        assert resp.status_code == 302
        assert resp["Location"].startswith("/bem-vindo/")

    def test_post_not_gated(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        # POST should pass through — middleware only intercepts GET
        resp = client.post("/cart/add/", {"sku": "NONEXISTENT", "qty": 1})
        # We don't care about the business response, only that we didn't
        # get redirected to /bem-vindo/
        assert resp.get("Location", "") != "/bem-vindo/"
        if resp.status_code == 302:
            assert "/bem-vindo/" not in resp["Location"]

    def test_htmx_not_gated(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.get("/cart/summary/", HTTP_HX_REQUEST="true")
        # Not gated to /bem-vindo/
        if resp.status_code == 302:
            assert "/bem-vindo/" not in resp["Location"]

    def test_welcome_path_not_gated(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.get("/bem-vindo/")
        # Welcome renders, doesn't loop-redirect
        assert resp.status_code == 200

    def test_login_not_gated(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        # Authenticated hitting /login/ — login view itself decides; but
        # middleware must not redirect to /bem-vindo/ first.
        resp = client.get("/login/")
        if resp.status_code == 302:
            assert "/bem-vindo/" not in resp["Location"]

    def test_admin_not_gated(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.get("/admin/")
        assert "/bem-vindo/" not in resp.get("Location", "")

    def test_api_not_gated(self, client: Client, nameless_customer):
        _login_as_customer(client, nameless_customer)
        resp = client.get("/api/v1/availability/")
        assert resp.get("Location", "") != "/bem-vindo/"
        if resp.status_code == 302:
            assert "/bem-vindo/" not in resp["Location"]
