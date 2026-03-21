"""
Attending configuration.

Usage in settings.py:
    GUESTMAN = {
        "DEFAULT_REGION": "BR",
        "EVENT_CLEANUP_DAYS": 90,
    }
"""

from dataclasses import dataclass
from typing import Any

from django.conf import settings


@dataclass
class AttendingSettings:
    """Attending configuration settings."""

    # Phone normalization default region
    DEFAULT_REGION: str = "BR"

    # ProcessedEvent cleanup
    EVENT_CLEANUP_DAYS: int = 90

    # Order history backend (for customer insights)
    ORDER_HISTORY_BACKEND: str = ""


def get_attending_settings() -> AttendingSettings:
    """Load settings from Django settings."""
    user_settings: dict[str, Any] = getattr(settings, "ATTENDING", {})
    return AttendingSettings(**user_settings)


class _LazySettings:
    """Lazy proxy that re-reads settings on every attribute access."""

    def __getattr__(self, name):
        return getattr(get_attending_settings(), name)


attending_settings = _LazySettings()
