"""
Offerman configuration.

Usage in settings.py:
    OFFERMAN = {
        "MAX_COLLECTION_DEPTH": 10,
        "BUNDLE_MAX_DEPTH": 5,
        "COST_BACKEND": None,  # e.g. "shopman.craftsman.adapters.offering.CraftingCostBackend"
        "PRICING_BACKEND": None,  # e.g. "framework.shopman.adapters.offering.StorefrontPricingBackend"
        "PROJECTION_BACKENDS": {},  # e.g. {"ifood": "myproj.offers.iFoodProjectionBackend"}
    }
"""

import importlib
import threading
from dataclasses import dataclass
from typing import Any

from django.conf import settings


@dataclass
class OffermanSettings:
    """Offerman configuration settings."""

    MAX_COLLECTION_DEPTH: int = 10
    BUNDLE_MAX_DEPTH: int = 5
    COST_BACKEND: str | None = None
    PRICING_BACKEND: str | None = None
    PROJECTION_BACKENDS: dict[str, str] | None = None


def get_offerman_settings() -> OffermanSettings:
    """Load settings from Django settings."""
    user_settings: dict[str, Any] = getattr(settings, "OFFERMAN", {})
    return OffermanSettings(**user_settings)


class _LazySettings:
    """Lazy proxy that re-reads settings on every attribute access."""

    def __getattr__(self, name):
        return getattr(get_offerman_settings(), name)


offerman_settings = _LazySettings()


# CostBackend singleton
_cost_backend_lock = threading.Lock()
_cost_backend_instance = None
_pricing_backend_lock = threading.Lock()
_pricing_backend_instance = None
_projection_backend_lock = threading.Lock()
_projection_backend_instances: dict[str, Any] = {}


def get_cost_backend():
    """
    Return the configured CostBackend instance, or None.

    Loads from OFFERMAN["COST_BACKEND"] setting (dotted path).
    If _cost_backend_instance was set directly (e.g. in tests), returns it as-is.
    """
    global _cost_backend_instance
    if _cost_backend_instance is not None:
        return _cost_backend_instance
    backend_path = offerman_settings.COST_BACKEND
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


def get_pricing_backend():
    """
    Return the configured PricingBackend instance, or None.

    Loads from OFFERMAN["PRICING_BACKEND"] setting (dotted path).
    If _pricing_backend_instance was set directly (e.g. in tests), returns it as-is.
    """
    global _pricing_backend_instance
    if _pricing_backend_instance is not None:
        return _pricing_backend_instance
    backend_path = offerman_settings.PRICING_BACKEND
    if not backend_path:
        return None
    with _pricing_backend_lock:
        if _pricing_backend_instance is None:
            module_path, cls_name = backend_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, cls_name)
            _pricing_backend_instance = cls()
    return _pricing_backend_instance


def reset_pricing_backend():
    """Reset PricingBackend singleton (for tests)."""
    global _pricing_backend_instance
    _pricing_backend_instance = None


def get_projection_backend(channel: str):
    """
    Return the configured CatalogProjectionBackend instance for a channel, or None.

    Loads from OFFERMAN["PROJECTION_BACKENDS"][channel] (dotted path).
    If _projection_backend_instances[channel] was set directly (e.g. in tests),
    returns it as-is.
    """
    existing = _projection_backend_instances.get(channel)
    if existing is not None:
        return existing

    backend_map = offerman_settings.PROJECTION_BACKENDS or {}
    backend_path = backend_map.get(channel)
    if not backend_path:
        return None

    with _projection_backend_lock:
        existing = _projection_backend_instances.get(channel)
        if existing is None:
            module_path, cls_name = backend_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            cls = getattr(module, cls_name)
            existing = cls()
            _projection_backend_instances[channel] = existing
    return existing


def reset_projection_backends():
    """Reset projection backend singletons (for tests)."""
    _projection_backend_instances.clear()
