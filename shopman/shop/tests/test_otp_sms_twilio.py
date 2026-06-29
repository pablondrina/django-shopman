from __future__ import annotations

import base64
from unittest import mock
from urllib.parse import parse_qs

from django.test import override_settings

from shopman.shop.adapters import otp_sms_twilio as sms

_CFG = {
    "account_sid": "ACxxxx",
    "auth_token": "secrettoken",
    "from_number": "+15551234567",
    "messaging_service_sid": "",
    "code_message": "",
    "timeout": 5,
}


class _FakeResp:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"sid": "SMxxxx"}'


@override_settings(SHOPMAN_SMS=dict(_CFG, account_sid="", auth_token=""))
def test_returns_false_without_credentials():
    assert sms.TwilioSMSSender().send_code("+5543999990000", "482913", "sms") is False


@override_settings(SHOPMAN_SMS=_CFG)
def test_sends_via_twilio_with_basic_auth_and_form_body():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["auth"] = request.headers.get("Authorization")
        captured["form"] = parse_qs(request.data.decode())
        return _FakeResp()

    with mock.patch.object(sms, "urlopen", fake_urlopen):
        ok = sms.TwilioSMSSender().send_code("+5543999990000", "482913", "sms")

    assert ok is True
    assert captured["url"] == "https://api.twilio.com/2010-04-01/Accounts/ACxxxx/Messages.json"
    expected_auth = "Basic " + base64.b64encode(b"ACxxxx:secrettoken").decode()
    assert captured["auth"] == expected_auth
    form = captured["form"]
    assert form["To"] == ["+5543999990000"]
    assert form["From"] == ["+15551234567"]
    assert "482913" in form["Body"][0]


@override_settings(SHOPMAN_SMS=dict(_CFG, from_number="", messaging_service_sid="MGxxxx"))
def test_uses_messaging_service_when_set():
    captured = {}

    def fake_urlopen(request, timeout=None):
        captured["form"] = parse_qs(request.data.decode())
        return _FakeResp()

    with mock.patch.object(sms, "urlopen", fake_urlopen):
        ok = sms.TwilioSMSSender().send_code("+5543999990000", "482913", "sms")

    assert ok is True
    assert captured["form"]["MessagingServiceSid"] == ["MGxxxx"]
    assert "From" not in captured["form"]


@override_settings(SHOPMAN_SMS=_CFG)
def test_returns_false_on_http_error():
    from urllib.error import HTTPError

    def boom(request, timeout=None):
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    with mock.patch.object(sms, "urlopen", boom):
        assert sms.TwilioSMSSender().send_code("+5543999990000", "482913", "sms") is False
