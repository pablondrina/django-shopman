"""
Crafting Offering Adapter — product/catalog information via Offering.

Supports both new CatalogProtocol and legacy ProductInfoBackend.

Usage:
    from shopman.craftsman.adapters.offering import get_catalog_backend

    backend = get_catalog_backend()
    info = backend.resolve("SKU-001")

Settings:
    CRAFTING = {
        "CATALOG_BACKEND": offerman.adapters.catalog.OfferingCatalogBackend",
    }
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


# Cached backend instance
_lock = threading.Lock()
_catalog_backend = None


def get_catalog_backend():
    """
    Return the configured catalog backend.

    Looks for CRAFTING.CATALOG_BACKEND first, falls back to
    CRAFTING.PRODUCT_INFO_BACKEND for backward compatibility.

    Returns:
        CatalogProtocol or ProductInfoBackend instance

    Raises:
        ImproperlyConfigured: If no backend is configured
    """
    global _catalog_backend

    if _catalog_backend is None:
        with _lock:
            if _catalog_backend is None:
                crafting_settings = getattr(settings, "CRAFTING", {})

                backend_path = (
                    crafting_settings.get("CATALOG_BACKEND")
                    or crafting_settings.get("PRODUCT_INFO_BACKEND")
                )

                if not backend_path:
                    raise ImproperlyConfigured(
                        "CRAFTING['CATALOG_BACKEND'] must be configured. "
                        "Example: offerman.adapters.catalog.OfferingCatalogBackend'"
                    )

                try:
                    backend_class = import_string(backend_path)
                    _catalog_backend = backend_class()
                    logger.debug("Loaded catalog backend: %s", backend_path)
                except ImportError as e:
                    raise ImproperlyConfigured(
                        f"Failed to import catalog backend '{backend_path}': {e}"
                    ) from e

    return _catalog_backend


# ── Backward compatibility ──

def get_product_info_backend():
    """Backward compat alias for get_catalog_backend()."""
    return get_catalog_backend()


def reset_catalog_backend() -> None:
    """Reset the cached backend. Useful for testing."""
    global _catalog_backend
    _catalog_backend = None


# backward compat alias
reset_product_info_backend = reset_catalog_backend
