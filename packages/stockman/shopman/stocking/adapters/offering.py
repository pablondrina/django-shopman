"""
Stocking Offering Adapter — SKU validation via Offering.

This adapter loads the configured SkuValidator from settings.

Usage:
    from shopman.stocking.adapters import get_sku_validator

    validator = get_sku_validator()
    result = validator.validate_sku("SKU-001")

Settings:
    STOCKING = {
        "SKU_VALIDATOR": "shopman.offering.adapters.sku_validator.OfferingSkuValidator",
    }

If SKU_VALIDATOR is not configured, get_sku_validator() raises ImproperlyConfigured.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

from shopman.stocking.protocols.sku import SkuValidator

if TYPE_CHECKING:
    from shopman.stocking.protocols.sku import SkuInfo, SkuValidationResult

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
        ImproperlyConfigured: If SKU_VALIDATOR is not configured or import fails
    """
    global _sku_validator

    if _sku_validator is None:
        with _lock:
            if _sku_validator is None:  # double-checked
                stocking_settings = getattr(settings, "STOCKING", {})
                validator_path = stocking_settings.get("SKU_VALIDATOR")

                if not validator_path:
                    raise ImproperlyConfigured(
                        "STOCKING['SKU_VALIDATOR'] must be configured. "
                        "Example: 'shopman.offering.adapters.sku_validator.OfferingSkuValidator'"
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
