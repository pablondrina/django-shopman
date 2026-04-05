"""Stocking Alerts configuration."""

from __future__ import annotations

from django.conf import settings


def get_alert_cooldown_minutes() -> int:
    """
    Return cooldown in minutes between re-notifications for the same alert.

    Configurable via settings.STOCKING_ALERT_COOLDOWN_MINUTES (default: 60).
    """
    return getattr(settings, "STOCKING_ALERT_COOLDOWN_MINUTES", 60)
