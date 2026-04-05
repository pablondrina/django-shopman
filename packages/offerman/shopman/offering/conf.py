"""
Offering configuration.

Usage in settings.py:
    OFFERING = {
        "MAX_COLLECTION_DEPTH": 10,
        "BUNDLE_MAX_DEPTH": 5,
        "COST_BACKEND": None,  # e.g. "shopman.crafting.adapters.offering.CraftingCostBackend"
    }
"""

import importlib
import threading
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings


@dataclass
class OfferingSettings:
    """Offering configuration settings."""

    MAX_COLLECTION_DEPTH: int = 10
    BUNDLE_MAX_DEPTH: int = 5
    COST_BACKEND: str | None = None


def get_offering_settings() -> OfferingSettings:
    """Load settings from Django settings."""
    user_settings: dict[str, Any] = getattr(settings, "OFFERING", {})
    return OfferingSettings(**user_settings)


class _LazySettings:
    """Lazy proxy that re-reads settings on every attribute access."""

    def __getattr__(self, name):
        return getattr(get_offering_settings(), name)


offering_settings = _LazySettings()


# CostBackend singleton
_cost_backend_lock = threading.Lock()
_cost_backend_instance = None


def get_cost_backend():
    """
    Return the configured CostBackend instance, or None.

    Loads from OFFERING["COST_BACKEND"] setting (dotted path).
    If _cost_backend_instance was set directly (e.g. in tests), returns it as-is.
    """
    global _cost_backend_instance
    if _cost_backend_instance is not None:
        return _cost_backend_instance
    backend_path = offering_settings.COST_BACKEND
    if not backend_path:
        return None
    with _cost_backend_lock:
        if _cost_backend_instance is None:
            module_path, cls_name = backend_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, cls_name)
            _cost_backend_instance = cls()
    return _cost_backend_instance


def reset_cost_backend():
    """Reset CostBackend singleton (for tests)."""
    global _cost_backend_instance
    _cost_backend_instance = None
