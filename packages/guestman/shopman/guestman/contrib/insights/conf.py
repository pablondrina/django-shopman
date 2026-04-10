"""
Guestman Insights configuration.

RFM thresholds are configurable via Django settings:

    GUESTMAN_INSIGHTS = {
        "RFM_RECENCY_THRESHOLDS": [(7, 5), (30, 4), (90, 3), (180, 2)],
        "RFM_FREQUENCY_THRESHOLDS": [(20, 5), (10, 4), (5, 3), (2, 2)],
        "RFM_MONETARY_THRESHOLDS": [(1000000, 5), (500000, 4), (200000, 3), (50000, 2)],
    }

Each threshold list is ordered descending by the boundary value.
The score for values below all thresholds defaults to 1.
"""
from __future__ import annotations

from django.conf import settings

# Defaults match the original hardcoded values in InsightService.
_DEFAULTS: dict[str, list[tuple[int, int]]] = {
    "RFM_RECENCY_THRESHOLDS": [(7, 5), (30, 4), (90, 3), (180, 2)],
    "RFM_FREQUENCY_THRESHOLDS": [(20, 5), (10, 4), (5, 3), (2, 2)],
    "RFM_MONETARY_THRESHOLDS": [(1000000, 5), (500000, 4), (200000, 3), (50000, 2)],
}


def _get(key: str) -> list[tuple[int, int]]:
    user: dict = getattr(settings, "GUESTMAN_INSIGHTS", {})
    return user.get(key, _DEFAULTS[key])


def get_recency_thresholds() -> list[tuple[int, int]]:
    return _get("RFM_RECENCY_THRESHOLDS")


def get_frequency_thresholds() -> list[tuple[int, int]]:
    return _get("RFM_FREQUENCY_THRESHOLDS")


def get_monetary_thresholds() -> list[tuple[int, int]]:
    return _get("RFM_MONETARY_THRESHOLDS")
