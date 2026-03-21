"""Attending protocols."""

from shopman.attending.protocols.customer import (
    CustomerBackend,
    AddressInfo,
    CustomerInfo,
    CustomerContext,
    CustomerValidationResult,
)
from shopman.attending.protocols.orders import (
    OrderHistoryBackend,
    OrderSummary,
    OrderStats,
)

__all__ = [
    # Customer
    "CustomerBackend",
    "AddressInfo",
    "CustomerInfo",
    "CustomerContext",
    "CustomerValidationResult",
    # Orders
    "OrderHistoryBackend",
    "OrderSummary",
    "OrderStats",
]
