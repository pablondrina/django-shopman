"""
Shopman Customer Protocols — Interfaces para backends de clientes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class AddressInfo:
    """Address information."""

    label: str
    formatted_address: str
    short_address: str
    complement: str | None = None
    delivery_instructions: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@dataclass(frozen=True)
class CustomerInfo:
    """Complete customer information for Session/Order."""

    code: str
    name: str
    customer_type: str = "individual"  # "individual" | "business"
    group_code: str | None = None
    listing_code: str | None = None
    phone: str | None = None
    email: str | None = None
    default_address: AddressInfo | None = None
    total_orders: int = 0
    is_vip: bool = False
    is_at_risk: bool = False
    favorite_products: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CustomerContext:
    """Complete context for personalization (LLM, greetings, etc.)."""

    info: CustomerInfo
    preferences: dict  # {category: {key: value}}
    recent_orders: list[dict] = field(default_factory=list)
    rfm_segment: str | None = None
    days_since_last_order: int | None = None
    recommended_products: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CustomerValidationResult:
    """Customer validation result."""

    valid: bool
    code: str
    info: CustomerInfo | None = None
    error_code: str | None = None
    message: str | None = None


@runtime_checkable
class CustomerBackend(Protocol):
    """
    Protocol para backends de clientes.
    """

    def get_customer(self, code: str) -> CustomerInfo | None:
        ...

    def validate_customer(self, code: str) -> CustomerValidationResult:
        ...

    def get_listing_code(self, customer_ref: str) -> str | None:
        ...

    def get_customer_context(self, code: str) -> CustomerContext | None:
        ...

    def record_order(self, customer_ref: str, order_data: dict) -> bool:
        ...
