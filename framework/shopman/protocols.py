"""
Channel protocols — contratos de backend consolidados.

Protocols que vivem no ordering core são re-exportados.
Protocols que viviam nos mini-apps são definidos inline aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

# ── Fiscal, Accounting ── (vivem no ordering core, re-export)
from shopman.ordering.protocols import (  # noqa: F401
    AccountingBackend,
    FiscalBackend,
)

# ── Payment ── (vivem no payments core, re-export)
from shopman.payments.protocols import (  # noqa: F401
    CaptureResult,
    GatewayIntent,
    PaymentBackend,
    PaymentStatus,
    RefundResult,
)

# Note: Stock no longer has a class-based protocol — the canonical entrypoint
# is the module `shopman.adapters.stock` (function-style adapter resolved via
# `get_adapter("stock")`). See ADR-001 for the protocol/adapter pattern.


# ── Customer (inline — era shopman.identification.protocols) ──


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
    customer_type: str = "individual"
    group_code: str | None = None
    listing_ref: str | None = None
    phone: str | None = None
    email: str | None = None
    default_address: AddressInfo | None = None
    total_orders: int = 0
    is_vip: bool = False
    is_at_risk: bool = False
    favorite_products: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CustomerContext:
    """Complete context for personalization."""

    info: CustomerInfo
    preferences: dict
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
    """Protocol para backends de clientes."""

    def get_customer(self, code: str) -> CustomerInfo | None: ...

    def validate_customer(self, code: str) -> CustomerValidationResult: ...

    def get_listing_ref(self, customer_ref: str) -> str | None: ...

    def get_customer_context(self, code: str) -> CustomerContext | None: ...

    def record_order(self, customer_ref: str, order_data: dict) -> bool: ...


# ── Notification (inline — era shopman.notifications.protocols) ──


@dataclass(frozen=True)
class NotificationResult:
    """Resultado do envio."""

    success: bool
    message_id: str | None = None
    error: str | None = None


# ── Pricing (inline — era shopman.pricing.protocols) ──


@runtime_checkable
class PricingBackend(Protocol):
    """Protocol para backends de precificação."""

    def get_price(
        self,
        sku: str,
        channel: Any,
        qty: int = 1,
    ) -> int | None: ...


__all__ = [
    # Payment
    "PaymentBackend",
    "GatewayIntent",
    "CaptureResult",
    "RefundResult",
    "PaymentStatus",
    # Fiscal
    "FiscalBackend",
    # Accounting
    "AccountingBackend",
    # Customer
    "CustomerBackend",
    "CustomerInfo",
    "CustomerContext",
    "CustomerValidationResult",
    "AddressInfo",
    # Notification
    "NotificationResult",
    # Pricing
    "PricingBackend",
]
