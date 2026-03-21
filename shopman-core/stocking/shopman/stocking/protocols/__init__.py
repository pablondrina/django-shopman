"""
Stocking Protocols.

Defines interfaces for external system integration.
"""

from shopman.stocking.protocols.production import (
    ProductionBackend,
    ProductionRequest,
    ProductionResult,
    ProductionStatus,
)
from shopman.stocking.protocols.sku import (
    SkuInfo,
    SkuValidationResult,
    SkuValidator,
)

__all__ = [
    "ProductionBackend",
    "ProductionRequest",
    "ProductionResult",
    "ProductionStatus",
    "SkuInfo",
    "SkuValidationResult",
    "SkuValidator",
]
