"""
Stocking configuration.

Usage in settings.py:
    STOCKING = {
        "SKU_VALIDATOR": "shopman.offering.adapters.sku_validator.OfferingSkuValidator",
        "HOLD_TTL_MINUTES": 30,
        "EXPIRED_BATCH_SIZE": 200,
        "VALIDATE_INPUT_SKUS": True,
    }
"""

from dataclasses import dataclass
from typing import Any

from django.conf import settings


@dataclass
class StockingSettings:
    """Stocking configuration settings."""

    # SKU validation backend (dotted path)
    SKU_VALIDATOR: str = ""

    # Default hold TTL in minutes (0 = no expiration)
    HOLD_TTL_MINUTES: int = 0

    # Batch size for release_expired processing
    EXPIRED_BATCH_SIZE: int = 200

    # Validate SKUs via external backend before stock operations
    VALIDATE_INPUT_SKUS: bool = True


def get_stocking_settings() -> StockingSettings:
    """Load settings from Django settings."""
    user_settings: dict[str, Any] = getattr(settings, "STOCKING", {})
    return StockingSettings(**{
        k: v for k, v in user_settings.items()
        if k in StockingSettings.__dataclass_fields__
    })


class _LazySettings:
    """Lazy proxy that re-reads settings on every attribute access."""

    def __getattr__(self, name):
        return getattr(get_stocking_settings(), name)


stocking_settings = _LazySettings()
