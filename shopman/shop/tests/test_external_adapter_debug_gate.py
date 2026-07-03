"""Trava de adapters externos: inertes em DEBUG (salvo opt-in) e no seed (sempre).

Regressão: rodar ``seed --flush`` disparava POSTs reais ao Comtele porque as
credenciais reais vivem no ambiente e ``is_available()`` do adapter SMS
retornava True. A trava (``shopman.shop.adapters._external.inert``) mantém
SMS/WhatsApp/OTP inertes em DEBUG sem opt-in — e ``suppress()`` (ativado pelo
seed) os mantém inertes em QUALQUER ambiente, porque dado sintético nunca
notifica gente de verdade.
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest
from django.test import override_settings

from shopman.shop.adapters import (
    _external,
    notification_manychat,
    notification_sms,
    notification_whatsapp,
    otp_sms_comtele,
)

COMTELE = {"api_key": "key-1", "route": "17", "timeout": 5}
MANYCHAT = {"api_token": "tok-1", "base_url": "https://api.manychat.com/fb", "timeout": 5}
WHATSAPP = {"PHONE_NUMBER_ID": "123", "ACCESS_TOKEN": "tok-1", "timeout": 5}


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _boom(*args, **kwargs):
    raise AssertionError("external network call must not happen in DEBUG")


# ── SMS de notificação ──────────────────────────────────────────────


@override_settings(DEBUG=True, SHOPMAN_SMS=COMTELE)
def test_sms_inert_in_debug_makes_no_call_and_reports_delivered():
    with patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=_boom):
        # Configurado (is_available True), mas em DEBUG não deve chamar a rede.
        assert notification_sms.is_available() is True
        assert notification_sms.send("+5543999990001", "order_confirmed", {}) is True


@override_settings(DEBUG=True, SHOPMAN_SMS=COMTELE, SHOPMAN_SMS_ALLOW_IN_DEBUG=True)
def test_sms_opt_in_restores_real_send_in_debug():
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append(request.full_url)
        return _FakeResponse(json.dumps({"hasError": False}).encode("utf-8"))

    with patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=fake_urlopen):
        assert notification_sms.send("+5543999990001", "order_confirmed", {}) is True
    assert calls == ["https://api.comtele.com.br/messages/sms/send"]


@override_settings(DEBUG=True, SHOPMAN_SMS=COMTELE, SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG=True)
def test_global_opt_in_restores_real_send_in_debug():
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append(request.full_url)
        return _FakeResponse(json.dumps({"hasError": False}).encode("utf-8"))

    with patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=fake_urlopen):
        assert notification_sms.send("+5543999990001", "order_confirmed", {}) is True
    assert len(calls) == 1


@override_settings(DEBUG=False, SHOPMAN_SMS=COMTELE)
def test_sms_sends_for_real_outside_debug():
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append(request.full_url)
        return _FakeResponse(json.dumps({"hasError": False}).encode("utf-8"))

    with patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=fake_urlopen):
        assert notification_sms.send("+5543999990001", "order_confirmed", {}) is True
    assert len(calls) == 1


# ── WhatsApp: ManyChat e Meta direto ────────────────────────────────


@override_settings(DEBUG=True, SHOPMAN_MANYCHAT=MANYCHAT)
def test_manychat_inert_in_debug():
    with patch("shopman.shop.adapters.notification_manychat.urlopen", side_effect=_boom):
        assert notification_manychat.send("5543999990001", "order_confirmed", {}) is True


@override_settings(DEBUG=True, SHOPMAN_WHATSAPP=WHATSAPP)
def test_whatsapp_inert_in_debug():
    with patch("shopman.shop.adapters.notification_whatsapp.urlopen", side_effect=_boom):
        assert notification_whatsapp.send("5543999990001", "order_confirmed", {}) is True


# ── OTP por SMS: inerte cai para o próximo sender (console) ──────────


@override_settings(DEBUG=True, SHOPMAN_SMS=COMTELE)
def test_otp_sms_inert_in_debug_returns_false_to_fall_through():
    with patch("shopman.shop.adapters.otp_sms_comtele.urlopen", side_effect=_boom):
        sender = otp_sms_comtele.ComteleSMSSender()
        # False → cadeia do Doorman (["sms","console"] em DEBUG) cai no console.
        assert sender.send_code("+5543999990001", "123456", "sms") is False


@override_settings(DEBUG=True, SHOPMAN_SMS=COMTELE, SHOPMAN_SMS_ALLOW_IN_DEBUG=True)
def test_otp_sms_opt_in_sends_in_debug():
    calls = []

    def fake_urlopen(request, timeout=0):
        calls.append(request.full_url)
        return _FakeResponse(json.dumps({"hasError": False}).encode("utf-8"))

    with patch("shopman.shop.adapters.otp_sms_comtele.urlopen", side_effect=fake_urlopen):
        sender = otp_sms_comtele.ComteleSMSSender()
        assert sender.send_code("+5543999990001", "123456", "sms") is True
    assert len(calls) == 1


# ── Supressão de processo (seed): vale mesmo FORA de DEBUG ──────────


@override_settings(DEBUG=False, SHOPMAN_SMS=COMTELE)
def test_suppress_blocks_external_even_outside_debug(monkeypatch):
    """Staging roda DEBUG=False com credenciais reais; o seed chama suppress()
    e nenhum adapter externo pode disparar — sem opt-out."""
    monkeypatch.setattr(_external, "_suppressed_reason", "seed")
    with patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=_boom):
        assert notification_sms.send("+5543999990001", "order_confirmed", {}) is True


@override_settings(DEBUG=False, SHOPMAN_SMS=COMTELE, SHOPMAN_ALLOW_EXTERNAL_IN_DEBUG=True)
def test_suppress_has_no_opt_out(monkeypatch):
    monkeypatch.setattr(_external, "_suppressed_reason", "seed")
    with patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=_boom):
        assert notification_sms.send("+5543999990001", "order_confirmed", {}) is True


# ── Seed não faz nenhuma chamada externa (qualquer ambiente) ────────


@pytest.mark.django_db(transaction=True)
@override_settings(
    DEBUG=False,
    SHOPMAN_SMS=COMTELE,
    SHOPMAN_MANYCHAT=MANYCHAT,
    SHOPMAN_WHATSAPP=WHATSAPP,
)
def test_seed_makes_no_external_calls_even_outside_debug(monkeypatch):
    """`seed --flush` cria e despacha directives de notificação (on_commit).

    transaction=True faz os callbacks de on_commit rodarem de verdade, como em
    produção — então isto exercita o caminho real Directive→handler→adapter.
    DEBUG=False reproduz o staging: o seed ativa suppress() e nenhum ``urlopen``
    dos adapters externos pode ser chamado.
    """
    from io import StringIO

    from django.core.management import call_command

    # O seed seta o global de supressão; o monkeypatch garante o restore no
    # teardown para não vazar para os demais testes do processo.
    monkeypatch.setattr(_external, "_suppressed_reason", None)
    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")

    with (
        patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=_boom),
        patch("shopman.shop.adapters.notification_manychat.urlopen", side_effect=_boom),
        patch("shopman.shop.adapters.notification_whatsapp.urlopen", side_effect=_boom),
        patch("shopman.shop.adapters.otp_sms_comtele.urlopen", side_effect=_boom),
    ):
        call_command("seed", "--flush", stdout=StringIO())
