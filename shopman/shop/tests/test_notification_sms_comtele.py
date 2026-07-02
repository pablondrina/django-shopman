"""Adapter de notificação SMS via Comtele (decisão go-live: SMS = Comtele).

Regressão do audit pré-go-live: o backend "sms" da cadeia de notificações era
um adapter Twilio lendo settings top-level que não existem — ``is_available()``
retornava False para sempre e o elo SMS era peso morto. Agora usa a MESMA
config Comtele do OTP (``SHOPMAN_SMS``), que já está fechada em produção.
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import pytest
from django.test import override_settings

from shopman.shop.adapters import notification_sms

COMTELE_SETTINGS = {"api_key": "key-1", "route": "17", "timeout": 5}


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@override_settings(SHOPMAN_SMS=COMTELE_SETTINGS)
def test_is_available_with_comtele_config():
    assert notification_sms.is_available() is True


@override_settings(SHOPMAN_SMS={})
def test_unavailable_without_config():
    assert notification_sms.is_available() is False
    assert notification_sms.send("+5543999990001", "order_confirmed", {}) is False


@override_settings(SHOPMAN_SMS=COMTELE_SETTINGS)
def test_send_posts_to_comtele_and_trusts_haserror_flag():
    captured = {}

    def fake_urlopen(request, timeout=0):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.headers)
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(json.dumps({"hasError": False}).encode("utf-8"))

    with patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=fake_urlopen):
        ok = notification_sms.send(
            "+55 (43) 99999-0001",
            "order_confirmed",
            {"order_ref": "ORD-1", "total": "R$ 56,00"},
        )

    assert ok is True
    assert captured["url"] == "https://api.comtele.com.br/messages/sms/send"
    assert captured["headers"]["X-api-key"] == "key-1"
    assert captured["payload"]["route"] == "17"
    assert captured["payload"]["receivers"] == ["5543999990001"]
    assert "ORD-1" in captured["payload"]["message"]


@override_settings(SHOPMAN_SMS=COMTELE_SETTINGS)
def test_send_returns_false_when_comtele_flags_error():
    def fake_urlopen(request, timeout=0):
        return _FakeResponse(json.dumps({"hasError": True, "message": "rota inválida"}).encode("utf-8"))

    with patch("shopman.shop.adapters.notification_sms.urlopen", side_effect=fake_urlopen):
        assert notification_sms.send("+5543999990001", "order_confirmed", {}) is False


@pytest.mark.django_db
@override_settings(SHOPMAN_SMS=COMTELE_SETTINGS)
def test_admin_template_wins_over_hardcoded_for_sms():
    """O texto editado no Admin (NotificationTemplate) vale para SMS e e-mail —
    não só para WhatsApp/ManyChat (regressão do audit)."""
    from shopman.shop.models import NotificationTemplate

    NotificationTemplate.objects.create(
        event="order_confirmed",
        subject="Pedido {order_ref} confirmado",
        body="Oi! Seu pedido {order_ref} está confirmado. Obrigado!",
        is_active=True,
    )

    assert notification_sms._build_message(
        "order_confirmed", {"order_ref": "ORD-9"}
    ) == "Oi! Seu pedido ORD-9 está confirmado. Obrigado!"
