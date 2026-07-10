"""Dev-safety: adapters externos ficam inertes em DEBUG (salvo opt-in).

Regressão: rodar ``seed --flush`` em dev disparava POSTs reais ao Comtele porque
as credenciais reais vivem no ``.env`` de dev e ``is_available()`` do adapter SMS
retornava True. A trava (``shopman.shop.adapters._external.inert_in_debug``) mantém
SMS/WhatsApp/OTP inertes em DEBUG — o dev server, um shell ou o seed nunca mais
tocam um provedor real sem opt-in explícito.
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest
from django.test import override_settings

from shopman.shop.adapters import (
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


# ── Seed em DEBUG não faz nenhuma chamada externa ───────────────────


@pytest.mark.django_db(transaction=True)
@override_settings(
    DEBUG=True,
    SHOPMAN_SMS=COMTELE,
    SHOPMAN_MANYCHAT=MANYCHAT,
    SHOPMAN_WHATSAPP=WHATSAPP,
)
def test_seed_makes_no_external_calls_in_debug(monkeypatch):
    """`seed --flush` cria e despacha directives de notificação (on_commit).

    transaction=True faz os callbacks de on_commit rodarem de verdade, como em
    produção — então isto exercita o caminho real Directive→handler→adapter. Com
    a trava, nenhum ``urlopen`` dos adapters externos pode ser chamado.
    """
    from io import StringIO

    from django.core.management import call_command

    monkeypatch.setenv("ADMIN_PASSWORD", "strong-seed-admin-password")

    with (
        patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=_boom),
        patch("shopman.shop.adapters.notification_manychat.urlopen", side_effect=_boom),
        patch("shopman.shop.adapters.notification_whatsapp.urlopen", side_effect=_boom),
        patch("shopman.shop.adapters.otp_sms_comtele.urlopen", side_effect=_boom),
    ):
        call_command("seed", "--flush", stdout=StringIO())
