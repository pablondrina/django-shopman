"""Guestman protocols."""

from shopman.guestman.protocols.customer import (
    AddressInfo,
    CustomerBackend,
    CustomerContext,
    CustomerInfo,
    CustomerValidationResult,
)
from shopman.guestman.protocols.orders import (
    OrderHistoryBackend,
    OrderStats,
    OrderSummary,
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
