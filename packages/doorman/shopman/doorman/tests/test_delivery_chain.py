"""Tests for AUTH-3: Delivery Fallback Chain."""
from __future__ import annotations

import pytest
from django.test import override_settings
from shopman.doorman.adapter import DefaultAuthAdapter
from shopman.doorman.conf import reset_adapter
from shopman.doorman.services.verification import AuthService

pytestmark = pytest.mark.django_db


class FakeSender:
    """Sender that always succeeds."""

    def __init__(self, succeed=True):
        self._succeed = succeed
        self.calls = []

    def send_code(self, target, code, method):
        self.calls.append((target, code, method))
        return self._succeed


class ExplodingSender:
    """Sender that raises an exception."""

    def __init__(self):
        self.calls = []

    def send_code(self, target, code, method):
        self.calls.append((target, code, method))
        raise ConnectionError("Sender down")


# ── Adapter-level tests ──────────────────────────────────────────────


class TestSendCodeWithFallback:
    def setup_method(self):
        reset_adapter()

    def teardown_method(self):
        reset_adapter()

    def test_no_chain_uses_default_sender(self):
        """Empty DELIVERY_CHAIN → uses default sender via send_code()."""
        adapter = DefaultAuthAdapter()
        adapter._sender = FakeSender(succeed=True)
        success, method = adapter.send_code_with_fallback("+5543999990001", "123456")
        assert success is True
        assert method == "whatsapp"

    @override_settings(DOORMAN={
        "DELIVERY_CHAIN": ["whatsapp", "sms", "email"],
        "DELIVERY_SENDERS": {
            "whatsapp": "shopman.doorman.senders.ConsoleSender",
            "sms": "shopman.doorman.senders.ConsoleSender",
            "email": "shopman.doorman.senders.ConsoleSender",
        },
    })
    def test_chain_succeeds_on_first(self):
        """First sender in chain succeeds → returns immediately."""
        adapter = DefaultAuthAdapter()
        success, method = adapter.send_code_with_fallback("+5543999990001", "123456")
        assert success is True
        assert method == "whatsapp"

    def test_chain_falls_back_to_second(self):
        """First sender fails → falls back to second."""
        adapter = DefaultAuthAdapter()
        fail_sender = FakeSender(succeed=False)
        ok_sender = FakeSender(succeed=True)
        adapter._chain_sender_whatsapp = fail_sender
        adapter._chain_sender_sms = ok_sender

        # Manually set the chain
        with override_settings(DOORMAN={
            "DELIVERY_CHAIN": ["whatsapp", "sms"],
            "DELIVERY_SENDERS": {
                "whatsapp": "shopman.doorman.senders.ConsoleSender",
                "sms": "shopman.doorman.senders.ConsoleSender",
            },
        }):
            success, method = adapter.send_code_with_fallback("+5543999990001", "123456")
        assert success is True
        assert method == "sms"
        assert len(fail_sender.calls) == 1
        assert len(ok_sender.calls) == 1

    def test_chain_falls_back_on_exception(self):
        """Sender raises exception → falls back to next."""
        adapter = DefaultAuthAdapter()
        exploding = ExplodingSender()
        ok_sender = FakeSender(succeed=True)
        adapter._chain_sender_whatsapp = exploding
        adapter._chain_sender_sms = ok_sender

        with override_settings(DOORMAN={
            "DELIVERY_CHAIN": ["whatsapp", "sms"],
            "DELIVERY_SENDERS": {
                "whatsapp": "shopman.doorman.senders.ConsoleSender",
                "sms": "shopman.doorman.senders.ConsoleSender",
            },
        }):
            success, method = adapter.send_code_with_fallback("+5543999990001", "123456")
        assert success is True
        assert method == "sms"

    def test_chain_exhausted_returns_false(self):
        """All senders fail → returns (False, last_method)."""
        adapter = DefaultAuthAdapter()
        fail1 = FakeSender(succeed=False)
        fail2 = FakeSender(succeed=False)
        adapter._chain_sender_whatsapp = fail1
        adapter._chain_sender_sms = fail2

        with override_settings(DOORMAN={
            "DELIVERY_CHAIN": ["whatsapp", "sms"],
            "DELIVERY_SENDERS": {
                "whatsapp": "shopman.doorman.senders.ConsoleSender",
                "sms": "shopman.doorman.senders.ConsoleSender",
            },
        }):
            success, method = adapter.send_code_with_fallback("+5543999990001", "123456")
        assert success is False
        assert method == "sms"

    def test_chain_skips_unconfigured_method(self):
        """Method in chain but not in DELIVERY_SENDERS → skipped."""
        adapter = DefaultAuthAdapter()
        ok_sender = FakeSender(succeed=True)
        adapter._chain_sender_sms = ok_sender

        with override_settings(DOORMAN={
            "DELIVERY_CHAIN": ["whatsapp", "sms"],
            "DELIVERY_SENDERS": {
                "sms": "shopman.doorman.senders.ConsoleSender",
                # whatsapp not in senders
            },
        }):
            success, method = adapter.send_code_with_fallback("+5543999990001", "123456")
        assert success is True
        assert method == "sms"

    @override_settings(DOORMAN={
        "DELIVERY_CHAIN": ["whatsapp", "sms", "email"],
    })
    def test_phone_chain_does_not_try_email(self):
        """Phone targets must not fall back to email delivery."""
        adapter = DefaultAuthAdapter()

        assert adapter.get_delivery_chain("+5543999990001") == ["whatsapp", "sms"]


# ── Service-level integration ────────────────────────────────────────


class TestRequestCodeWithFallback:
    def setup_method(self):
        reset_adapter()

    def teardown_method(self):
        reset_adapter()

    @override_settings(DOORMAN={
        "CUSTOMER_RESOLVER_CLASS": "shopman.guestman.adapters.auth.CustomerResolver",
    })
    def test_request_code_records_actual_delivery_method(self):
        """request_code() records the actual delivery method used by fallback."""
        from shopman.doorman.models import VerificationCode

        # Use custom sender that succeeds
        sender = FakeSender(succeed=True)
        result = AuthService.request_code(
            target_value="+5543999990001",
            purpose="login",
            delivery_method="whatsapp",
            sender=sender,
        )
        assert result.success is True
        code = VerificationCode.objects.get(pk=result.code_id)
        assert code.delivery_method == "whatsapp"
        assert code.status == "sent"

    @override_settings(DOORMAN={
        "CUSTOMER_RESOLVER_CLASS": "shopman.guestman.adapters.auth.CustomerResolver",
        "DELIVERY_CHAIN": ["whatsapp", "sms"],
        "DELIVERY_SENDERS": {
            "whatsapp": "shopman.doorman.senders.ConsoleSender",
            "sms": "shopman.doorman.senders.ConsoleSender",
        },
    })
    def test_request_code_uses_fallback_chain(self):
        """request_code() uses adapter fallback when no custom sender."""
        from shopman.doorman.models import VerificationCode

        result = AuthService.request_code(
            target_value="+5543999990001",
            purpose="login",
            delivery_method="whatsapp",
        )
        assert result.success is True
        code = VerificationCode.objects.get(pk=result.code_id)
        # ConsoleSender succeeds on first method
        assert code.delivery_method == "whatsapp"
        assert code.status == "sent"
