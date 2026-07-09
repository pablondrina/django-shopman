"""Start leve do login por WhatsApp (ACCESS-LINK-UNIFICATION, F2).

O ``/start/`` agora só guarda o contexto do site (sacola anônima + destino) sob um
código ``NB-XxXx`` de uso único e devolve o deep link ``wa.me`` já preenchido. Sem
handshake/token/poll/SSE: a identidade é o número que envia a mensagem; o login
acontece depois, pelo access link que o ManyChat devolve (ver ``AccessLinkCreateView``).

As views legado ``confirm``/``status``/SSE (reverse-OTP) ainda existem no arquivo mas
estão mortas neste fluxo; são removidas em F4 (inventário no ACCESS-LINK-UNIFICATION-PLAN.md).
"""
from __future__ import annotations

import json

import pytest
from django.core.cache import cache
from django.test import Client, override_settings
from shopman.doorman.services.link_state import pop_state

pytestmark = pytest.mark.django_db

WA_SETTINGS = {"number": "554333231997", "ttl_seconds": 600}


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


def _post_json(client: Client, url: str, data: dict, **extra):
    return client.post(url, data=json.dumps(data), content_type="application/json", **extra)


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_returns_code_and_deep_link(client: Client):
    resp = _post_json(client, "/api/v1/auth/whatsapp/start/", {})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"].startswith("NB-")
    assert body["wa_number"] == "554333231997"
    assert "wa.me/554333231997" in body["deep_link"]
    # O código vai pré-preenchido na mensagem (é o que o ManyChat casa no fluxo do site).
    assert body["code"] in body["deep_link"]


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_stores_cart_and_next_under_code(client: Client):
    # Sacola anônima na sessão + destino → viajam no estado do código (uso único).
    session = client.session
    session["cart_session_key"] = "sk_anon_42"
    session.save()
    resp = _post_json(client, "/api/v1/auth/whatsapp/start/", {"next": "/checkout"})
    code = resp.json()["code"]
    assert pop_state(code) == {"cart_session_key": "sk_anon_42", "next": "/checkout"}


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_without_context_still_issues_code(client: Client):
    resp = _post_json(client, "/api/v1/auth/whatsapp/start/", {})
    body = resp.json()
    assert body["code"].startswith("NB-")
    # Estado vazio → o create degrada para o link genérico (sem sacola/destino).
    assert pop_state(body["code"]) == {}


@override_settings(SHOPMAN_WA_VERIFY=WA_SETTINGS)
def test_start_ignores_open_redirect_next(client: Client):
    resp = _post_json(
        client, "/api/v1/auth/whatsapp/start/", {"next": "https://evil.example/phish"}
    )
    code = resp.json()["code"]
    # _safe_next descarta destino externo/protocol-relative (guard de open-redirect).
    assert "next" not in (pop_state(code) or {})
