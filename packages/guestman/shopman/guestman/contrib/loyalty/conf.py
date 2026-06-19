"""
Guestman Loyalty configuration.

Tier thresholds and the default stamp-card target are configurable two ways,
in priority order:

1. A resolver registered by the host application (the orchestrator wires one
   from its own store config). This keeps guestman decoupled — guestman never
   imports the host; the host pushes a callable in.
2. Django settings, as a static fallback::

       GUESTMAN_LOYALTY = {
           "TIER_THRESHOLDS": [(5000, "platinum"), (2000, "gold"), (500, "silver"), (0, "bronze")],
           "DEFAULT_STAMPS_TARGET": 10,
       }

   ``TIER_THRESHOLDS`` is ordered descending by lifetime_points threshold.
"""
from __future__ import annotations

from collections.abc import Callable

from django.conf import settings

# Default matches the original hardcoded _TIER_THRESHOLDS.
_DEFAULT_TIER_THRESHOLDS: list[tuple[int, str]] = [
    (5000, "platinum"),
    (2000, "gold"),
    (500, "silver"),
    (0, "bronze"),
]

# Matches LoyaltyAccount.stamps_target model default.
_DEFAULT_STAMPS_TARGET = 10

_tier_thresholds_resolver: Callable[[], list[tuple[int, str]]] | None = None
_default_stamps_target_resolver: Callable[[], int | None] | None = None


def set_tier_thresholds_resolver(
    resolver: Callable[[], list[tuple[int, str]]] | None,
) -> None:
    """Register (or clear with ``None``) a callable returning the tier ladder.

    The resolver returns ``[(threshold, name)]`` ordered descending. Lets the
    host drive thresholds from its own config without guestman depending on it.
    """
    global _tier_thresholds_resolver
    _tier_thresholds_resolver = resolver


def set_default_stamps_target_resolver(
    resolver: Callable[[], int | None] | None,
) -> None:
    """Register (or clear with ``None``) a callable returning the default
    stamp-card target for newly enrolled accounts."""
    global _default_stamps_target_resolver
    _default_stamps_target_resolver = resolver


def get_tier_thresholds() -> list[tuple[int, str]]:
    if _tier_thresholds_resolver is not None:
        resolved = _tier_thresholds_resolver()
        if resolved:
            return resolved
    user: dict = getattr(settings, "GUESTMAN_LOYALTY", {})
    return user.get("TIER_THRESHOLDS", _DEFAULT_TIER_THRESHOLDS)


def get_default_stamps_target() -> int:
    if _default_stamps_target_resolver is not None:
        resolved = _default_stamps_target_resolver()
        if resolved is not None:
            return resolved
    user: dict = getattr(settings, "GUESTMAN_LOYALTY", {})
    return user.get("DEFAULT_STAMPS_TARGET", _DEFAULT_STAMPS_TARGET)
