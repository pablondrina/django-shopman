"""
Contract tests for adapters.

Verifies each adapter module exports the required functions with correct signatures.
Also tests get_adapter() resolution with and without channel overrides.
"""

from __future__ import annotations

import inspect
from importlib import import_module
from unittest.mock import MagicMock, patch

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
            if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        ]

        for required in required_params:
            assert required in param_names, (
                f"{module_path}.{func_name}() missing parameter: {required}"
                f" (has: {param_names})"
            )


# ── Stock adapter contract ──


class TestStockInternalContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.adapters.stock_internal", STOCK_CONTRACT)

    def test_has_extra_utility_functions(self):
        mod = import_module("shopman.adapters.stock_internal")
        assert callable(getattr(mod, "release_holds_for_reference", None))
        assert callable(getattr(mod, "receive_return", None))


# ── Payment adapter contracts ──


class TestPaymentMockContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.adapters.payment_mock", PAYMENT_CONTRACT)


class TestPaymentEfiContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.adapters.payment_efi", PAYMENT_CONTRACT)

    def test_has_check_gateway_status(self):
        mod = import_module("shopman.adapters.payment_efi")
        assert callable(getattr(mod, "check_gateway_status", None))


class TestPaymentStripeContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.adapters.payment_stripe", PAYMENT_CONTRACT)

    def test_has_handle_webhook(self):
        mod = import_module("shopman.adapters.payment_stripe")
        assert callable(getattr(mod, "handle_webhook", None))


# ── Notification adapter contracts ──


class TestNotificationConsoleContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.adapters.notification_console", NOTIFICATION_CONTRACT)


class TestNotificationEmailContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.adapters.notification_email", NOTIFICATION_CONTRACT)


class TestNotificationManychatContract:
    def test_exports_all_functions(self):
        _check_contract("shopman.adapters.notification_manychat", NOTIFICATION_CONTRACT)


# ── get_adapter() resolution tests ──


class TestGetAdapter:
    def test_payment_with_method_returns_module(self):
        from shopman.adapters import get_adapter

        adapter = get_adapter("payment", method="pix")
        assert adapter is not None
        assert hasattr(adapter, "create_intent")
        assert hasattr(adapter, "capture")

    def test_payment_default_returns_mock(self):
        from shopman.adapters import get_adapter

        adapter = get_adapter("payment", method="pix")
        assert adapter.__name__ == "shopman.adapters.payment_mock"

    def test_stock_returns_internal(self):
        from shopman.adapters import get_adapter

        adapter = get_adapter("stock")
        assert adapter is not None
        assert adapter.__name__ == "shopman.adapters.stock_internal"
        assert hasattr(adapter, "check_availability")
        assert hasattr(adapter, "create_hold")

    def test_notification_returns_console_default(self):
        from shopman.adapters import get_adapter

        adapter = get_adapter("notification", method="console")
        assert adapter is not None
        assert adapter.__name__ == "shopman.adapters.notification_console"

    def test_channel_override(self):
        from shopman.adapters import get_adapter

        channel = MagicMock()
        channel.config = {
            "notification_adapter": "shopman.adapters.notification_console",
        }

        adapter = get_adapter("notification", channel=channel)
        assert adapter is not None
        assert adapter.__name__ == "shopman.adapters.notification_console"

    def test_channel_override_takes_precedence(self):
        from shopman.adapters import get_adapter

        channel = MagicMock()
        channel.config = {
            "payment_adapter": "shopman.adapters.payment_mock",
        }

        adapter = get_adapter("payment", method="pix", channel=channel)
        assert adapter.__name__ == "shopman.adapters.payment_mock"

    def test_counter_method_returns_none(self):
        from shopman.adapters import get_adapter

        adapter = get_adapter("payment", method="counter")
        assert adapter is None

    def test_fiscal_default_returns_none(self):
        from shopman.adapters import get_adapter

        adapter = get_adapter("fiscal")
        assert adapter is None

    @patch("shopman.adapters.settings")
    def test_custom_settings_override(self, mock_settings):
        mock_settings.SHOPMAN_PAYMENT_ADAPTERS = {
            "pix": "shopman.adapters.payment_efi",
        }
        mock_settings.SHOPMAN_NOTIFICATION_ADAPTERS = None
        mock_settings.SHOPMAN_STOCK_ADAPTER = None
        mock_settings.SHOPMAN_FISCAL_ADAPTER = None

        from shopman.adapters import get_adapter

        adapter = get_adapter("payment", method="pix")
        assert adapter is not None
        assert adapter.__name__ == "shopman.adapters.payment_efi"


# ── Console adapter behavior ──


class TestConsoleAdapterBehavior:
    def test_send_returns_true(self):
        from shopman.adapters.notification_console import send

        result = send("test@example.com", "order_confirmed", {"order_ref": "ORD-001"})
        assert result is True

    def test_is_available_returns_true(self):
        from shopman.adapters.notification_console import is_available

        assert is_available() is True
