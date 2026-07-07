"""Reverse-OTP de WhatsApp: start, confirm (server-to-server) e status/login.

Cobre o fluxo invertido: o storefront gera token + deep link, o ManyChat confirma
S2S (autenticado pela DOORMAN_ACCESS_LINK_API_KEY) e o polling autentica a sessão.
Token vive só no cache (Valkey em prod, LocMem no teste).
"""
from __future__ import annotations

import copy
import json

import pytest
from django.conf import settings as dj_settings
from django.core.cache import cache
from django.test import Client, override_settings

pytestmark = pytest.mark.django_db

API_KEY = "s2s-test-key"
WA_SETTINGS = {"number": "554333231997", "ttl_seconds": 600, "token_prefix": "V-"}


def _doorman_with_key(key: str = API_KEY) -> dict:
    """Copia o DOORMAN real e injeta a chave S2S (preserva DELIVERY_SENDERS etc.)."""
    d = copy.deepcopy(dj_settings.DOORMAN)
    d["ACCESS_LINK_API_KEY"] = key
    return d


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _post_json(client: Client, url: str, data: dict, **extra):
    return client.post(url, data=json.dumps(data), content_type="application/json", **extra)


def _confirm(client: Client, token: str, phone: str, *, key: str = API_KEY):
    return _post_json(
        client,
        "/api/v1/auth/whatsapp/confirm/",
        {"token": token, "phone": phone},
        HTTP_AUTHORIZATION=f"Bearer {key}",
    )


# ── start ──────────────────────────────────────────────────────────────────


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_returns_token_and_deep_link(client: Client):
    resp = _post_json(client, "/api/v1/auth/whatsapp/start/", {"phone": "+5543999990001"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token"].startswith("V-")
    assert body["wa_number"] == "554333231997"
    assert "wa.me/554333231997" in body["deep_link"]
    assert body["token"] in body["deep_link"]
    assert body["expires_in"] == 600


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_without_phone_still_issues_token(client: Client):
    resp = _post_json(client, "/api/v1/auth/whatsapp/start/", {})
    assert resp.status_code == 200
    assert resp.json()["token"].startswith("V-")


# ── confirm (server-to-server) ──────────────────────────────────────────────


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_confirm_requires_api_key(client: Client):
    start = _post_json(client, "/api/v1/auth/whatsapp/start/", {}).json()
    # Sem header de autorização → 401 (fail-closed fora de DEBUG).
    resp = _post_json(
        client,
        "/api/v1/auth/whatsapp/confirm/",
        {"token": start["token"], "phone": "+5543999990002"},
    )
    assert resp.status_code == 401


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=_doorman_with_key())
def test_confirm_wrong_api_key_rejected(client: Client):
    start = _post_json(client, "/api/v1/auth/whatsapp/start/", {}).json()
    resp = _confirm(client, start["token"], "+5543999990002", key="wrong-key")
    assert resp.status_code == 401


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=_doorman_with_key())
def test_confirm_unknown_token_404(client: Client):
    resp = _confirm(client, "V-NOPE99", "+5543999990004")
    assert resp.status_code == 404
    assert resp.json()["ok"] is False


# ── status + login ──────────────────────────────────────────────────────────


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_status_unknown_token_is_expired(client: Client):
    body = _post_json(client, "/api/v1/auth/whatsapp/status/", {"token": "V-GONE99"}).json()
    assert body["status"] == "expired"
    assert body["is_authenticated"] is False


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=_doorman_with_key())
def test_full_flow_confirm_then_status_authenticates(client: Client):
    phone = "+5543999990003"
    start = _post_json(client, "/api/v1/auth/whatsapp/start/", {"phone": phone}).json()
    token = start["token"]

    # Antes da confirmação: pending, não autenticado.
    pending = _post_json(client, "/api/v1/auth/whatsapp/status/", {"token": token}).json()
    assert pending["status"] == "pending"
    assert pending["is_authenticated"] is False

    # ManyChat confirma S2S com a chave.
    confirm = _confirm(client, token, phone)
    assert confirm.status_code == 200
    assert confirm.json()["ok"] is True
    assert confirm.json()["matched"] is True

    # Polling agora: verificado e sessão autenticada (auto-create do cliente).
    done = _post_json(client, "/api/v1/auth/whatsapp/status/", {"token": token}).json()
    assert done["status"] == "verified"
    assert done["is_authenticated"] is True
    assert done["customer_phone"]


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=_doorman_with_key())
def test_confirm_is_idempotent(client: Client):
    phone = "+5543999990006"
    token = _post_json(client, "/api/v1/auth/whatsapp/start/", {"phone": phone}).json()["token"]
    first = _confirm(client, token, phone)
    second = _confirm(client, token, phone)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["reason"] == "already_verified"


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=_doorman_with_key())
def test_confirm_extracts_token_from_full_message(client: Client):
    """ManyChat pode mandar a mensagem inteira do cliente; o serviço extrai o token."""
    phone = "+5543999990007"
    token = _post_json(client, "/api/v1/auth/whatsapp/start/", {"phone": phone}).json()["token"]
    resp = _confirm(client, f"Meu codigo de verificacao e {token.lower()}", phone)
    assert resp.status_code == 200
    assert resp.json()["ok"] is True


# ── nome trazido do WhatsApp ────────────────────────────────────────────────


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=_doorman_with_key())
def test_brought_name_is_suggested_for_confirmation(client: Client):
    """O nome do perfil do WhatsApp volta como welcome_suggested_name para confirmar."""
    phone = "+5543999990008"
    token = _post_json(client, "/api/v1/auth/whatsapp/start/", {"phone": phone}).json()["token"]
    confirm = client.post(
        "/api/v1/auth/whatsapp/confirm/",
        data=json.dumps({"token": token, "phone": phone, "name": "Joana Ferreira"}),
        content_type="application/json",
        HTTP_AUTHORIZATION=f"Bearer {API_KEY}",
    )
    assert confirm.status_code == 200

    done = _post_json(client, "/api/v1/auth/whatsapp/status/", {"token": token}).json()
    assert done["status"] == "verified"
    assert done["is_authenticated"] is True
    # Cliente novo: traz o nome como sugestão, mas ainda pede confirmação.
    assert done["welcome_suggested_name"] == "Joana Ferreira"
    assert done["requires_welcome"] is True


# ── bind de sessão (anti-fixação) ───────────────────────────────────────────


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=_doorman_with_key())
def test_status_binds_to_originating_session(client: Client):
    """Só a sessão que iniciou o fluxo autentica; outro navegador fica pending."""
    phone = "+5543999990009"
    token = _post_json(client, "/api/v1/auth/whatsapp/start/", {"phone": phone}).json()["token"]
    _confirm(client, token, phone)

    # Navegador diferente (outra sessão) não deve autenticar.
    other = Client()
    intruder = _post_json(other, "/api/v1/auth/whatsapp/status/", {"token": token}).json()
    assert intruder["status"] == "pending"
    assert intruder["is_authenticated"] is False

    # A sessão original autentica normalmente.
    legit = _post_json(client, "/api/v1/auth/whatsapp/status/", {"token": token}).json()
    assert legit["status"] == "verified"
    assert legit["is_authenticated"] is True


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS, DOORMAN=_doorman_with_key())
def test_phone_mismatch_is_flagged(client: Client):
    """Número digitado ≠ número que confirmou pelo WhatsApp → flag, não silêncio."""
    token = _post_json(
        client, "/api/v1/auth/whatsapp/start/", {"phone": "+5543999990010"}
    ).json()["token"]
    _confirm(client, token, "+5543999990011")
    done = _post_json(client, "/api/v1/auth/whatsapp/status/", {"token": token}).json()
    assert done["status"] == "verified"
    assert done.get("phone_mismatch") is True
