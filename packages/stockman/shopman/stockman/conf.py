"""
Stockman configuration.

Usage in settings.py:
    STOCKMAN = {
        "SKU_VALIDATOR": "shopman.stockman.adapters.noop.NoopSkuValidator",
        "HOLD_TTL_MINUTES": 30,
        "EXPIRED_BATCH_SIZE": 200,
        "VALIDATE_INPUT_SKUS": True,
    }
"""

from dataclasses import dataclass
from typing import Any

from django.conf import settings


@dataclass
class StockmanSettings:
    """Stockman configuration settings."""

    # SKU validation backend (dotted path)
    SKU_VALIDATOR: str = "shopman.stockman.adapters.noop.NoopSkuValidator"

    # Default hold TTL in minutes (0 = no expiration)
    HOLD_TTL_MINUTES: int = 0

    # Batch size for release_expired processing
    EXPIRED_BATCH_SIZE: int = 200

    # Validate SKUs via external backend before stock operations
    VALIDATE_INPUT_SKUS: bool = True


def get_stockman_settings() -> StockmanSettings:
    """Load settings from Django settings."""
    user_settings: dict[str, Any] = getattr(settings, "STOCKMAN", {})
    return StockmanSettings(**{
        k: v for k, v in user_settings.items()
        if k in StockmanSettings.__dataclass_fields__
    })


class _LazySettings:
    """Lazy proxy that re-reads settings on every attribute access."""

    def __getattr__(self, name):
        return getattr(get_stockman_settings(), name)


stockman_settings = _LazySettings()
