"""
Stockman SKU validation adapter.

This adapter loads the configured SkuValidator from settings.

Usage:
    from shopman.stockman.adapters import get_sku_validator

    validator = get_sku_validator()
    result = validator.validate_sku("SKU-001")

Settings:
    STOCKMAN = {
        "SKU_VALIDATOR": "shopman.offerman.adapters.sku_validator.SkuValidator",
    }
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string
from shopman.stockman.protocols.sku import SkuValidator

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Cached validator instance
_lock = threading.Lock()
_sku_validator: SkuValidator | None = None


def get_sku_validator() -> SkuValidator:
    """
    Return the configured SKU validator.

    Returns:
        SkuValidator instance

    Raises:
        ImproperlyConfigured: If the configured validator import fails
    """
    global _sku_validator

    if _sku_validator is None:
        with _lock:
            if _sku_validator is None:  # double-checked
                stockman_settings = getattr(settings, "STOCKMAN", {})
                validator_path = stockman_settings.get(
                    "SKU_VALIDATOR",
                    "shopman.stockman.adapters.noop.NoopSkuValidator",
                )

                try:
                    validator_class = import_string(validator_path)
                    _sku_validator = validator_class()
                    logger.debug("Loaded SKU validator: %s", validator_path)
                except ImportError as e:
                    raise ImproperlyConfigured(
                        f"Failed to import SKU validator '{validator_path}': {e}"
                    ) from e

    return _sku_validator


def reset_sku_validator() -> None:
    """Reset the cached validator. Useful for testing."""
    global _sku_validator
    _sku_validator = None
