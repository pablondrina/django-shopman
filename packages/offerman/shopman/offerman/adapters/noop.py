"""
Noop CostBackend -- default for projects that don't need cost tracking.
"""

from __future__ import annotations

from shopman.offerman.protocols.cost import CostBackend


class NoopCostBackend:
    """CostBackend that returns None for every SKU."""

    def get_cost(self, sku: str) -> int | None:
        """Always returns None -- no cost tracking."""
        return None


# Verify protocol compliance at import time.
if not isinstance(NoopCostBackend(), CostBackend):
    raise TypeError("NoopCostBackend does not implement CostBackend protocol")
