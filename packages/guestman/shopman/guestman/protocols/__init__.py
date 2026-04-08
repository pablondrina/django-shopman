"""Customers protocols."""

from shopman.guestman.protocols.customer import (
    CustomerBackend,
    AddressInfo,
    CustomerInfo,
    CustomerContext,
    CustomerValidationResult,
)
from shopman.guestman.protocols.orders import (
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
