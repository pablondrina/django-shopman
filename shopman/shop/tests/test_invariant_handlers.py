"""
Invariant: every handler in ALL_HANDLERS must be importable and have a topic or code.

This ensures no stale references remain after handler deletions.
"""

from __future__ import annotations

import importlib

import pytest

from shopman.shop.handlers import ALL_HANDLERS


class TestHandlersInvariant:
    @pytest.mark.parametrize("dotted_path", ALL_HANDLERS)
    def test_handler_is_importable(self, dotted_path: str):
        """Every handler in ALL_HANDLERS must be importable."""
        module_path, class_name = dotted_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        assert cls is not None

    @pytest.mark.parametrize("dotted_path", ALL_HANDLERS)
    def test_handler_has_topic_or_code(self, dotted_path: str):
        """Every handler must have a 'topic' (directive handler) or 'code' (modifier/validator)."""
        module_path, class_name = dotted_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        cls = getattr(module, class_name)
        instance = cls() if not _needs_args(cls) else None
        if instance:
            has_identifier = hasattr(instance, "topic") or hasattr(instance, "code")
            assert has_identifier, f"{class_name} must have 'topic' or 'code'"

    def test_no_orphan_customer_handler(self):
        """CustomerEnsureHandler must NOT be in ALL_HANDLERS (deleted in WP-B)."""
        for path in ALL_HANDLERS:
            assert "CustomerEnsureHandler" not in path

    def test_no_orphan_checkout_defaults_handler(self):
        """CheckoutInferDefaultsHandler must NOT be in ALL_HANDLERS (deleted in WP-B)."""
        for path in ALL_HANDLERS:
            assert "CheckoutInferDefaultsHandler" not in path


def _needs_args(cls) -> bool:
    """Check if __init__ requires arguments beyond self."""
    import inspect
    sig = inspect.signature(cls.__init__)
    params = [p for p in sig.parameters.values() if p.name != "self"]
    return any(p.default is inspect.Parameter.empty for p in params)
