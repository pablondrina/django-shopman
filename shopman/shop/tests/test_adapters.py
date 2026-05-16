"""
Contract tests for adapters.

Verifies each adapter module exports the required functions with correct signatures.
Also tests get_adapter() resolution with and without channel overrides.
"""

from __future__ import annotations

import inspect
from importlib import import_module
from unittest.mock import patch

from django.test import override_settings

# ── Contract definitions ──

STOCK_CONTRACT = {
    "check_availability": ["sku", "qty"],
    "create_hold": ["sku", "qty", "ttl_minutes"],
    "fulfill_hold": ["hold_id"],
    "release_holds": ["hold_ids"],
}

PAYMENT_CONTRACT = {
    "create_intent": ["order_ref", "amount_q", "method"],
    "capture": ["intent_ref"],
    "refund": ["intent_ref"],
    "cancel": ["intent_ref"],
    "get_status": ["intent_ref"],
}

NOTIFICATION_CONTRACT = {
    "send": ["recipient", "template"],
    "is_available": [],
}


def _manychat_test_resolver(recipient: str) -> int:
    assert recipient == "+5543999998888"
    return 123456


def _check_contract(module_path: str, contract: dict[str, list[str]]):
    """Verify a module exports all required functions with expected parameters."""
    mod = import_module(module_path)

    for func_name, required_params in contract.items():
        assert hasattr(mod, func_name), (
            f"{module_path} missing function: {func_name}"
        )

        func = getattr(mod, func_name)
        assert callable(func), (
            f"{module_path}.{func_name} is not callable"
        )

        sig = inspect.signature(func)
        param_names = [
            p.name
            for p in sig.parameters.values()
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
        ]

        for required in required_params:
            assert required in param_names, (
                f"{module_path}.{func_name}() missing parameter: {required}"
                f" (has: {param_names})"
            )


# ── Stock adapter contract ──


class TestStockContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.shop.adapters.stock", STOCK_CONTRACT)

    def test_has_extra_utility_functions(self):
        mod = import_module("shopman.shop.adapters.stock")
        assert callable(getattr(mod, "release_holds_for_reference", None))
        assert callable(getattr(mod, "receive_return", None))


class TestChannelScopeResolution:
    """``get_channel_scope`` must resolve ``excluded_positions`` from
    ``ChannelConfig.stock`` so the scope gate (shared by check and reserve)
    sees the configured denylist for a given channel."""

    def test_scope_reads_excluded_positions_from_channel_config(self, db):
        from shopman.shop.adapters import stock
        from shopman.shop.models import Channel

        Channel.objects.update_or_create(
            ref="test-remote",
            defaults={
                "name": "Test Remote",
                "is_active": True,
                "config": {"stock": {"excluded_positions": ["ontem"]}},
            },
        )
        scope = stock.get_channel_scope("test-remote")
        assert scope["excluded_positions"] == ["ontem"]

    def test_scope_defaults_empty_when_channel_has_no_denylist(self, db):
        from shopman.shop.adapters import stock
        from shopman.shop.models import Channel

        Channel.objects.update_or_create(
            ref="test-pos",
            defaults={
                "name": "Test POS",
                "is_active": True,
                "config": {"stock": {"check_on_commit": True}},
            },
        )
        scope = stock.get_channel_scope("test-pos")
        assert scope["excluded_positions"] == []


# ── Payment adapter contracts ──


class TestPaymentMockContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.shop.adapters.payment_mock", PAYMENT_CONTRACT)


class TestPaymentEfiContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.shop.adapters.payment_efi", PAYMENT_CONTRACT)

    def test_has_check_gateway_status(self):
        mod = import_module("shopman.shop.adapters.payment_efi")
        assert callable(getattr(mod, "check_gateway_status", None))


class TestPaymentStripeContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.shop.adapters.payment_stripe", PAYMENT_CONTRACT)

    def test_has_handle_webhook(self):
        mod = import_module("shopman.shop.adapters.payment_stripe")
        assert callable(getattr(mod, "handle_webhook", None))


# ── Notification adapter contracts ──


class TestNotificationConsoleContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.shop.adapters.notification_console", NOTIFICATION_CONTRACT)


class TestNotificationEmailContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.shop.adapters.notification_email", NOTIFICATION_CONTRACT)


class TestNotificationManychatContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.shop.adapters.notification_manychat", NOTIFICATION_CONTRACT)

    @override_settings(SHOPMAN_MANYCHAT={
        "api_token": "token",
        "resolver": "shopman.shop.tests.test_adapters._manychat_test_resolver",
    })
    def test_resolver_path_can_target_dotted_callable(self):
        mod = import_module("shopman.shop.adapters.notification_manychat")

        subscriber_id = mod._resolve_subscriber("+5543999998888", mod._get_config())

        assert subscriber_id == 123456


class TestOTPManychatSender:
    def test_resolver_path_can_target_dotted_callable(self):
        mod = import_module("shopman.shop.adapters.otp_manychat")
        config = {
            "api_token": "token",
            "resolver": "shopman.shop.tests.test_adapters._manychat_test_resolver",
        }

        subscriber_id = mod._resolve_subscriber("+5543999998888", config)

        assert subscriber_id == 123456

    @override_settings(SHOPMAN_MANYCHAT={
        "api_token": "token",
        "resolver": "shopman.shop.tests.test_adapters._manychat_test_resolver",
    })
    def test_send_code_uses_direct_content(self):
        mod = import_module("shopman.shop.adapters.otp_manychat")

        with patch.object(mod.ManychatOTPSender, "_api_call", return_value=True) as api_call:
            result = mod.ManychatOTPSender().send_code("+5543999998888", "123456", "whatsapp")

        assert result is True
        endpoint, payload, _config = api_call.call_args.args
        assert endpoint == "/sending/sendContent"
        assert payload["subscriber_id"] == 123456
        assert "flow_ns" not in payload
        assert "flow_token" not in payload


class TestDottedAdapterImport:
    def test_imports_nested_class_method(self):
        from shopman.shop.adapters._dotted import import_dotted_attr

        resolver = import_dotted_attr(
            "shopman.guestman.contrib.manychat.resolver.ManychatSubscriberResolver.resolve"
        )

        assert callable(resolver)


# ── get_adapter() resolution tests ──


class TestGetAdapter:
    def test_payment_with_method_returns_module(self):
        from shopman.shop.adapters import get_adapter

        adapter = get_adapter("payment", method="pix")
        assert adapter is not None
        assert hasattr(adapter, "create_intent")
        assert hasattr(adapter, "capture")

    def test_payment_default_returns_mock(self):
        from shopman.shop.adapters import get_adapter

        adapter = get_adapter("payment", method="pix")
        assert adapter.__name__ == "shopman.shop.adapters.payment_mock"

    def test_stock_returns_module(self):
        from shopman.shop.adapters import get_adapter

        adapter = get_adapter("stock")
        assert adapter is not None
        assert adapter.__name__ == "shopman.shop.adapters.stock"
        assert hasattr(adapter, "check_availability")
        assert hasattr(adapter, "create_hold")

    def test_notification_returns_console_default(self):
        from shopman.shop.adapters import get_adapter

        adapter = get_adapter("notification", method="console")
        assert adapter is not None
        assert adapter.__name__ == "shopman.shop.adapters.notification_console"

    def test_cash_method_returns_none(self):
        from shopman.shop.adapters import get_adapter

        adapter = get_adapter("payment", method="cash")
        assert adapter is None

    def test_fiscal_default_returns_none(self):
        from shopman.shop.adapters import get_adapter

        adapter = get_adapter("fiscal")
        assert adapter is None

    @patch("shopman.shop.adapters.settings")
    def test_custom_settings_override(self, mock_settings):
        mock_settings.SHOPMAN_PAYMENT_ADAPTERS = {
            "pix": "shopman.shop.adapters.payment_efi",
        }
        mock_settings.SHOPMAN_NOTIFICATION_ADAPTERS = None
        mock_settings.SHOPMAN_STOCK_ADAPTER = None
        mock_settings.SHOPMAN_FISCAL_ADAPTER = None

        from shopman.shop.adapters import get_adapter

        adapter = get_adapter("payment", method="pix")
        assert adapter is not None
        assert adapter.__name__ == "shopman.shop.adapters.payment_efi"


# ── Console adapter behavior ──


class TestConsoleAdapterBehavior:
    def test_send_returns_true(self):
        from shopman.shop.adapters.notification_console import send

        result = send("test@example.com", "order_confirmed", {"order_ref": "ORD-001"})
        assert result is True

    def test_is_available_returns_true(self):
        from shopman.shop.adapters.notification_console import is_available

        assert is_available() is True
