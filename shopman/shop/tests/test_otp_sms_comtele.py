from __future__ import annotations

import json
from unittest import mock

from django.test import override_settings

from shopman.shop.adapters import otp_sms_comtele as comtele

_CFG = {
    "api_key": "1bf12b60-0fa9-433b-a294-932266ca27bb",
    "route": "17",
    "tag": "shopman-otp",
    "code_message": "",
    "timeout": 5,
}


class _Resp:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._body


@override_settings(SHOPMAN_SMS=dict(_CFG, api_key=""))
def test_returns_false_without_api_key():
    assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False


@override_settings(SHOPMAN_SMS=dict(_CFG, route=""))
def test_returns_false_without_route():
    assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False


@override_settings(SHOPMAN_SMS=_CFG)
def test_sends_with_x_api_key_header_and_json_body():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["key"] = request.headers.get("X-api-key")  # urllib title-cases header keys
        captured["ctype"] = request.headers.get("Content-type")
        captured["body"] = json.loads(request.data.decode())
        return _Resp({"hasError": False, "message": None, "totalRecords": 1, "errors": None})

    with mock.patch.object(comtele, "urlopen", fake_urlopen):
        ok = comtele.ComteleSMSSender().send_code("+55 43 99999-0000", "482913", "sms")

    assert ok is True
    assert captured["url"] == "https://api.comtele.com.br/messages/sms/send"
    assert captured["key"] == "1bf12b60-0fa9-433b-a294-932266ca27bb"
    assert captured["ctype"] == "application/json"
    body = captured["body"]
    assert body["receivers"] == ["5543999990000"]  # array, digits only
    assert body["route"] == "17"
    assert body["tag"] == "shopman-otp"
    assert "482913" in body["message"]


@override_settings(SHOPMAN_SMS=_CFG)
def test_returns_false_when_api_reports_error():
    def fake_urlopen(request, timeout=None):
        return _Resp({"hasError": True, "message": "saldo insuficiente", "errors": []})

    with mock.patch.object(comtele, "urlopen", fake_urlopen):
        assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False


@override_settings(SHOPMAN_SMS=_CFG)
def test_returns_false_on_http_error():
    from urllib.error import HTTPError

    def boom(request, timeout=None):
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    with mock.patch.object(comtele, "urlopen", boom):
        assert comtele.ComteleSMSSender().send_code("+5543999990000", "482913", "sms") is False
