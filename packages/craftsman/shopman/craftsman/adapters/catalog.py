"""
Craftsman Offerman Adapter — product/catalog information via Offerman.

Usage:
    from shopman.craftsman.adapters.catalog import get_catalog_backend

    backend = get_catalog_backend()
    info = backend.resolve("SKU-001")

Settings:
    CRAFTSMAN = {
        "CATALOG_BACKEND": "shopman.offerman.adapters.catalog_backend.OffermanCatalogBackend",
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

    Returns:
        Catalog backend instance

    Raises:
        ImproperlyConfigured: If no backend is configured
    """
    global _catalog_backend

    if _catalog_backend is None:
        with _lock:
            if _catalog_backend is None:
                craftsman_settings = getattr(settings, "CRAFTSMAN", {})

                backend_path = craftsman_settings.get("CATALOG_BACKEND")

                if not backend_path:
                    raise ImproperlyConfigured(
                        "CRAFTSMAN['CATALOG_BACKEND'] must be configured. "
                        "Example: 'shopman.offerman.adapters.catalog_backend.OffermanCatalogBackend'"
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

def reset_catalog_backend() -> None:
    """Reset the cached backend. Useful for testing."""
    global _catalog_backend
    _catalog_backend = None
