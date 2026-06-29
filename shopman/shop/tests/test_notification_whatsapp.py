from __future__ import annotations

import io
import json
from unittest import mock

from django.test import override_settings

from shopman.shop.adapters import notification_whatsapp as wa

_CFG = {
    "PHONE_NUMBER_ID": "1234567890",
    "ACCESS_TOKEN": "EAAtoken",
    "GRAPH_VERSION": "v21.0",
    "DEFAULT_LANG": "pt_BR",
    "timeout": 5,
    "templates": {
        "order_confirmed": {"name": "pedido_confirmado", "body": ["order_ref", "total"]},
    },
}


class _FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _ok_response():
    return _FakeResp(json.dumps({"messages": [{"id": "wamid.ABC"}]}).encode())


@override_settings(SHOPMAN_WHATSAPP=dict(_CFG, PHONE_NUMBER_ID="", ACCESS_TOKEN=""))
def test_is_available_false_without_creds():
    assert wa.is_available() is False


@override_settings(SHOPMAN_WHATSAPP=_CFG)
def test_is_available_true_with_creds():
    assert wa.is_available() is True


@override_settings(SHOPMAN_WHATSAPP=_CFG)
def test_send_uses_template_payload_when_mapped():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["auth"] = request.headers.get("Authorization")
        return _ok_response()

    with mock.patch.object(wa, "urlopen", fake_urlopen):
        ok = wa.send("+55 43 99999-0000", "order_confirmed", {"order_ref": "ORD-1", "total": "R$ 15,00"})

    assert ok is True
    assert captured["url"] == "https://graph.facebook.com/v21.0/1234567890/messages"
    assert captured["auth"] == "Bearer EAAtoken"
    body = captured["body"]
    assert body["to"] == "5543999990000"  # digits-only E.164
    assert body["type"] == "template"
    assert body["template"]["name"] == "pedido_confirmado"
    assert body["template"]["language"]["code"] == "pt_BR"
    params = body["template"]["components"][0]["parameters"]
    assert [p["text"] for p in params] == ["ORD-1", "R$ 15,00"]


@override_settings(SHOPMAN_WHATSAPP=_CFG)
def test_send_falls_back_to_text_when_event_not_mapped():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["body"] = json.loads(request.data.decode())
        return _ok_response()

    with mock.patch.object(wa, "urlopen", fake_urlopen):
        ok = wa.send("5543999990000", "order_ready_pickup", {"order_ref": "ORD-9"})

    assert ok is True
    assert captured["body"]["type"] == "text"
    assert "ORD-9" in captured["body"]["text"]["body"]


@override_settings(SHOPMAN_WHATSAPP=dict(_CFG, PHONE_NUMBER_ID="", ACCESS_TOKEN=""))
def test_send_returns_false_without_creds():
    assert wa.send("5543999990000", "order_confirmed", {}) is False
