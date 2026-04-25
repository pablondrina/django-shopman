"""Optional integration points for host/orchestrator apps.

Orderman must stay installable without django-shopman. When a host project
provides a shop.Channel model, Orderman can use it for convenience UI/API
surfaces through Django's app registry without importing the orchestrator.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps


def get_shop_channel_model() -> type[Any] | None:
    """Return the optional shop.Channel model when the host app provides it."""
    try:
        return apps.get_model("shop", "Channel")
    except LookupError:
        return None
