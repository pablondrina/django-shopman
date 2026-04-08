"""
Customers Loyalty configuration.

Tier thresholds are configurable via Django settings:

    GUESTMAN_LOYALTY = {
        "TIER_THRESHOLDS": [(5000, "platinum"), (2000, "gold"), (500, "silver"), (0, "bronze")],
    }

The list is ordered descending by lifetime_points threshold.
"""
from __future__ import annotations

from django.conf import settings

# Default matches the original hardcoded _TIER_THRESHOLDS.
_DEFAULT_TIER_THRESHOLDS: list[tuple[int, str]] = [
    (5000, "platinum"),
    (2000, "gold"),
    (500, "silver"),
    (0, "bronze"),
]


def get_tier_thresholds() -> list[tuple[int, str]]:
    user: dict = getattr(settings, "GUESTMAN_LOYALTY", {})
    return user.get("TIER_THRESHOLDS", _DEFAULT_TIER_THRESHOLDS)
