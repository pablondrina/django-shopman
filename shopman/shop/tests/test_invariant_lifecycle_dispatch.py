"""
Invariant: lifecycle.py must stay table/function driven.

All behavior is driven by ChannelConfig; dispatch() is a pure function.
"""

from __future__ import annotations

import ast
import inspect

import shopman.shop.lifecycle as lifecycle_module


class TestLifecycleDispatchShape:
    def test_no_class_definitions_in_lifecycle(self):
        """lifecycle.py must not define any classes."""
        source = inspect.getsource(lifecycle_module)
        tree = ast.parse(source)
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        assert classes == [], f"lifecycle.py must have zero classes, found: {classes}"

    def test_no_lifecycle_registry(self):
        """lifecycle.py must not have a dynamic registry."""
        assert not hasattr(lifecycle_module, "_registry"), (
            "lifecycle.py must not have a _registry; use explicit phase handler maps"
        )

    def test_no_dynamic_lifecycle_resolver(self):
        """lifecycle.py must not have a dynamic resolver — dispatch reads config directly."""
        assert not hasattr(lifecycle_module, "get_lifecycle"), (
            "lifecycle.py must not have get_lifecycle() (use config-driven dispatch)"
        )

    def test_dispatch_is_callable(self):
        """dispatch() must exist and be callable."""
        assert callable(getattr(lifecycle_module, "dispatch", None))
