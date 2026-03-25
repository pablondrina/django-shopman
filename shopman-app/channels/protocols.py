"""
Channel protocols — contratos de backend consolidados.

Protocols que vivem no ordering core são re-exportados.
Protocols que viviam nos mini-apps são definidos inline aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
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
from shopman.payments.protocols import (
    GatewayIntent as PaymentIntent,  # Backward compat alias
)

# ── Stock (inline — era shopman.inventory.protocols) ──


@dataclass(frozen=True)
class AvailabilityResult:
    """Resultado de verificação de disponibilidade."""

    available: bool
    available_qty: Decimal
    message: str | None = None


@dataclass(frozen=True)
class HoldResult:
    """Resultado de criação de reserva."""

    success: bool
    hold_id: str | None = None
    error_code: str | None = None
    message: str | None = None
    expires_at: datetime | None = None
    is_planned: bool = False


@dataclass(frozen=True)
class Alternative:
    """Produto alternativo sugerido."""

    sku: str
    name: str
    available_qty: Decimal


@runtime_checkable
class StockBackend(Protocol):
    """Protocol para backends de estoque."""

    def check_availability(
        self,
        sku: str,
        quantity: Decimal,
        target_date: date | None = None,
    ) -> AvailabilityResult: ...

    def create_hold(
        self,
        sku: str,
        quantity: Decimal,
        expires_at: datetime | None = None,
        reference: str | None = None,
        target_date: date | None = None,
    ) -> HoldResult: ...

    def release_hold(self, hold_id: str) -> None: ...

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None: ...

    def get_alternatives(self, sku: str, quantity: Decimal) -> list[Alternative]: ...

    def release_holds_for_reference(self, reference: str) -> int: ...

    def receive_return(
        self,
        sku: str,
        quantity: Decimal,
        *,
        reference: str | None = None,
        reason: str = "Devolução",
    ) -> None: ...


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


@runtime_checkable
class NotificationBackend(Protocol):
    """Protocol para backends de notificação."""

    def send(
        self,
        *,
        event: str,
        recipient: str,
        context: dict[str, Any],
    ) -> NotificationResult: ...


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
    # Stock
    "StockBackend",
    "AvailabilityResult",
    "HoldResult",
    "Alternative",
    # Payment
    "PaymentBackend",
    "PaymentIntent",
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
    "NotificationBackend",
    "NotificationResult",
    # Pricing
    "PricingBackend",
]
