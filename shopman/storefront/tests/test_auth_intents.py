"""Unit tests for storefront/intents/auth.py."""
from __future__ import annotations

from unittest.mock import MagicMock

from shopman.storefront.intents.auth import (
    clean_display_name,
    interpret_device_check_login,
    interpret_login,
    interpret_request_code,
    interpret_verify_code,
    interpret_welcome,
    needs_confirmation,
)


def _post(data: dict, session: dict | None = None, get: dict | None = None, customer=None):
    req = MagicMock()
    req.POST = data
    req.GET = get or {}
    req.session = session or {}
    req.customer = customer
    return req


# ── clean_display_name ────────────────────────────────────────────────────────


class TestCleanDisplayName:
    def test_empty(self):
        assert clean_display_name("") == ""

    def test_clean_passthrough(self):
        assert clean_display_name("João Silva") == "João Silva"

    def test_emoji_stripped(self):
        assert clean_display_name("Joana 🥐") == "Joana"

    def test_whitespace_collapsed(self):
        assert clean_display_name("Joao   Oliveira") == "Joao Oliveira"


# ── needs_confirmation ────────────────────────────────────────────────────────


class TestNeedsConfirmation:
    def test_empty_needs(self):
        assert needs_confirmation("") is True

    def test_clean_ok(self):
        assert needs_confirmation("Joana") is False

    def test_emoji_needs(self):
        assert needs_confirmation("Joana 🥐") is True

    def test_suspect_char_needs(self):
        assert needs_confirmation("João & Maria") is True


# ── interpret_login (step=phone) ──────────────────────────────────────────────


class TestInterpretLoginPhone:
    def test_missing_phone_returns_error(self):
        req = _post({"step": "phone", "phone": ""})
        result = interpret_login(req)
        assert result.intent is None
        assert "phone" in result.errors

    def test_invalid_phone_returns_error(self):
        req = _post({"step": "phone", "phone": "abc"})
        result = interpret_login(req)
        assert result.intent is None
        assert "phone" in result.errors

    def test_valid_phone_returns_intent(self):
        req = _post({"step": "phone", "phone": "43999998888"})
        result = interpret_login(req)
        assert result.intent is not None
        assert result.intent.step == "phone"
        assert result.intent.phone.startswith("+")
        assert result.intent.delivery_method == "whatsapp"

    def test_ios_autofill_zero_before_ddd_returns_intent(self):
        req = _post({"step": "phone", "phone": "(043) 98404-9009"})
        result = interpret_login(req)
        assert result.intent is not None
        assert result.intent.phone == "+5543984049009"

    def test_delivery_method_sms(self):
        req = _post({"step": "phone", "phone": "43999998888", "delivery_method": "sms"})
        result = interpret_login(req)
        assert result.intent is not None
        assert result.intent.delivery_method == "sms"

    def test_invalid_delivery_method_defaults_to_whatsapp(self):
        req = _post({"step": "phone", "phone": "43999998888", "delivery_method": "pigeon"})
        result = interpret_login(req)
        assert result.intent is not None
        assert result.intent.delivery_method == "whatsapp"

    def test_next_url_from_get(self):
        req = _post({"step": "phone", "phone": "43999998888"}, get={"next": "/menu/"})
        result = interpret_login(req)
        assert result.intent.next_url == "/menu/"


# ── interpret_login (step=name) ───────────────────────────────────────────────


class TestInterpretLoginName:
    def test_missing_name_returns_error(self):
        req = _post({"step": "name", "name": ""}, session={"login_phone": "+5543999998888"})
        result = interpret_login(req)
        assert result.intent is None
        assert "name" in result.errors

    def test_valid_name_returns_intent(self):
        req = _post({"step": "name", "name": "Joana"}, session={"login_phone": "+5543999998888"})
        result = interpret_login(req)
        assert result.intent is not None
        assert result.intent.step == "name"
        assert result.intent.name == "Joana"
        assert result.intent.phone is None


# ── interpret_request_code ────────────────────────────────────────────────────


class TestInterpretRequestCode:
    def test_missing_phone(self):
        req = _post({"phone": ""})
        result = interpret_request_code(req)
        assert result.intent is None
        assert "phone" in result.errors

    def test_invalid_phone(self):
        req = _post({"phone": "notaphone"})
        result = interpret_request_code(req)
        assert result.intent is None
        assert "phone" in result.errors

    def test_valid_phone(self):
        req = _post({"phone": "43999998888"})
        result = interpret_request_code(req)
        assert result.intent is not None
        assert result.intent.phone.startswith("+")

    def test_ios_autofill_zero_before_ddd(self):
        req = _post({"phone": "(043) 98404-9009"})
        result = interpret_request_code(req)
        assert result.intent is not None
        assert result.intent.phone == "+5543984049009"


# ── interpret_verify_code ─────────────────────────────────────────────────────


class TestInterpretVerifyCode:
    def test_missing_code(self):
        req = _post({"phone": "43999998888", "code": ""})
        result = interpret_verify_code(req)
        assert result.intent is None

    def test_missing_phone(self):
        req = _post({"phone": "", "code": "123456"})
        result = interpret_verify_code(req)
        assert result.intent is None

    def test_invalid_phone(self):
        req = _post({"phone": "abc", "code": "123456"})
        result = interpret_verify_code(req)
        assert result.intent is None
        assert "phone" in result.errors

    def test_valid_inputs(self):
        req = _post({"phone": "43999998888", "code": "123456"})
        result = interpret_verify_code(req)
        assert result.intent is not None
        assert result.intent.phone.startswith("+")
        assert result.intent.code == "123456"

    def test_code_accepts_pasted_format(self):
        req = _post({"phone": "43999998888", "code": "123-456"})
        result = interpret_verify_code(req)
        assert result.intent is not None
        assert result.intent.code == "123456"

    def test_code_requires_six_digits(self):
        req = _post({"phone": "43999998888", "code": "12345"})
        result = interpret_verify_code(req)
        assert result.intent is None
        assert result.errors["code"] == "Informe os 6 números do código."

    def test_form_data_carries_raw_phone(self):
        req = _post({"phone": "43999998888", "code": "123456"})
        result = interpret_verify_code(req)
        assert result.form_data["phone"] == "43999998888"


# ── interpret_device_check_login ──────────────────────────────────────────────


class TestInterpretDeviceCheckLogin:
    def test_missing_phone(self):
        req = _post({"phone": ""})
        result = interpret_device_check_login(req)
        assert result.intent is None

    def test_valid_phone(self):
        req = _post({"phone": "43999998888"})
        result = interpret_device_check_login(req)
        assert result.intent is not None
        assert result.intent.phone.startswith("+")


# ── interpret_welcome ─────────────────────────────────────────────────────────


class TestInterpretWelcome:
    def _customer_info(self):
        info = MagicMock()
        info.uuid = "test-uuid-1234"
        return info

    def test_unauthenticated_returns_auth_error(self):
        req = _post({"name": "Joana"}, customer=None)
        result = interpret_welcome(req)
        assert result.intent is None
        assert "auth" in result.errors

    def test_empty_name_returns_error(self):
        req = _post({"name": ""}, customer=self._customer_info())
        result = interpret_welcome(req)
        assert result.intent is None
        assert "name" in result.errors

    def test_whitespace_only_is_empty(self):
        req = _post({"name": "   "}, customer=self._customer_info())
        result = interpret_welcome(req)
        assert result.intent is None
        assert "name" in result.errors

    def test_valid_name_returns_intent(self):
        req = _post({"name": "Joana Silva"}, customer=self._customer_info())
        result = interpret_welcome(req)
        assert result.intent is not None
        assert result.intent.name == "Joana Silva"
        assert result.intent.customer_uuid == "test-uuid-1234"

    def test_emoji_stripped_from_name(self):
        req = _post({"name": "Joana 🥐"}, customer=self._customer_info())
        result = interpret_welcome(req)
        assert result.intent is not None
        assert result.intent.name == "Joana"

    def test_next_url_from_get(self):
        req = _post({"name": "Joana"}, get={"next": "/menu/"}, customer=self._customer_info())
        result = interpret_welcome(req)
        assert result.intent.next_url == "/menu/"

    def test_open_redirect_blocked(self):
        req = _post(
            {"name": "Joana"},
            get={"next": "https://evil.example.com/"},
            customer=self._customer_info(),
        )
        result = interpret_welcome(req)
        assert result.intent.next_url == "/"

    def test_protocol_relative_blocked(self):
        req = _post(
            {"name": "Joana"},
            get={"next": "//evil.example.com/"},
            customer=self._customer_info(),
        )
        result = interpret_welcome(req)
        assert result.intent.next_url == "/"
