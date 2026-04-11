"""
Invariant: lifecycle.py must have zero Flow classes.

All behavior is driven by ChannelConfig — no Flow subclasses.
dispatch() is a pure function.
"""

from __future__ import annotations

import ast
import inspect

import shopman.lifecycle as lifecycle_module


class TestNoLegacyFlowClasses:
    def test_no_class_definitions_in_lifecycle(self):
        """lifecycle.py must not define any classes."""
        source = inspect.getsource(lifecycle_module)
        tree = ast.parse(source)
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        assert classes == [], f"lifecycle.py must have zero classes, found: {classes}"

    def test_no_flow_registry(self):
        """lifecycle.py must not have a _registry dict for Flow classes."""
        assert not hasattr(lifecycle_module, "_registry"), (
            "lifecycle.py must not have a _registry (Flow class registry was removed)"
        )

    def test_no_get_flow_function(self):
        """lifecycle.py must not have get_flow() — dispatch reads config directly."""
        assert not hasattr(lifecycle_module, "get_flow"), (
            "lifecycle.py must not have get_flow() (replaced by config-driven dispatch)"
        )

    def test_dispatch_is_callable(self):
        """dispatch() must exist and be callable."""
        assert callable(getattr(lifecycle_module, "dispatch", None))
