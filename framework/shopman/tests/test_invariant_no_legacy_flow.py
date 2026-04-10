"""
Invariant: flows.py must have zero Flow classes.

After WP-B, all behavior is driven by ChannelConfig — no Flow subclasses.
dispatch() is a pure function.
"""

from __future__ import annotations

import ast
import inspect

import shopman.flows as flows_module


class TestNoLegacyFlowClasses:
    def test_no_class_definitions_in_flows(self):
        """flows.py must not define any classes."""
        source = inspect.getsource(flows_module)
        tree = ast.parse(source)
        classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        assert classes == [], f"flows.py must have zero classes, found: {classes}"

    def test_no_flow_registry(self):
        """flows.py must not have a _registry dict for Flow classes."""
        assert not hasattr(flows_module, "_registry"), (
            "flows.py must not have a _registry (Flow class registry was removed)"
        )

    def test_no_get_flow_function(self):
        """flows.py must not have get_flow() — dispatch reads config directly."""
        assert not hasattr(flows_module, "get_flow"), (
            "flows.py must not have get_flow() (replaced by config-driven dispatch)"
        )

    def test_dispatch_is_callable(self):
        """dispatch() must exist and be callable."""
        assert callable(getattr(flows_module, "dispatch", None))
