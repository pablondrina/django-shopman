"""Customers protocols."""

from shopman.customers.protocols.customer import (
    CustomerBackend,
    AddressInfo,
    CustomerInfo,
    CustomerContext,
    CustomerValidationResult,
)
from shopman.customers.protocols.orders import (
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
