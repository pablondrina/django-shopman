"""
Shopman Noop Pricing Adapter -- No-op modifier for development and testing.
"""

from __future__ import annotations

from typing import Any


class NoopPricingModifier:
    """
    Modifier that leaves item prices unchanged.
    """

    code = "pricing.noop"
    order = 10

    def apply(self, *, channel: Any, session: Any, ctx: dict) -> None:
        """No-op: items retain their current prices without modification."""
        pass
