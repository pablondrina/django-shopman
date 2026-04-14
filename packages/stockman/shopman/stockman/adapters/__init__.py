"""
Stockman Adapters.

Implementations of protocols for external systems.
"""

from shopman.stockman.adapters.noop import NoopSkuValidator
from shopman.stockman.adapters.production import ProductionBackend, get_production_backend
from shopman.stockman.adapters.sku_validation import (
    get_sku_validator,
    reset_sku_validator,
)

__all__ = [
    "ProductionBackend",
    "NoopSkuValidator",
    "get_production_backend",
    "get_sku_validator",
    "reset_sku_validator",
]
