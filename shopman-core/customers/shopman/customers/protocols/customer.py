"""Customer protocols."""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class AddressInfo:
    """Address information."""

    label: str
    formatted_address: str
    short_address: str
    complement: str | None
    delivery_instructions: str | None
    latitude: float | None
    longitude: float | None


@dataclass(frozen=True)
class CustomerInfo:
    """Complete customer information for Session/Order."""

    ref: str
    name: str
    customer_type: str  # "individual" | "business"
    group_ref: str | None
    listing_ref: str | None
    phone: str | None
    email: str | None
    default_address: AddressInfo | None = None
    # Summary insights
    total_orders: int = 0
    is_vip: bool = False
    is_at_risk: bool = False
    favorite_products: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CustomerContext:
    """Complete context for personalization (LLM, greetings, etc.)."""

    info: CustomerInfo
    preferences: dict[str, dict]  # {category: {key: value}}
    recent_orders: list[dict]  # Last N orders
    rfm_segment: str | None
    days_since_last_order: int | None
    recommended_products: list[str]  # Suggested SKUs


@dataclass(frozen=True)
class CustomerValidationResult:
    """Validation result."""

    valid: bool
    ref: str
    info: CustomerInfo | None = None
    error_code: str | None = None
    message: str | None = None


@runtime_checkable
class CustomerBackend(Protocol):
    """Protocol for customer system integration."""

    def get_customer(self, ref: str) -> CustomerInfo | None:
        """Get customer information by ref."""
        ...

    def validate_customer(self, ref: str) -> CustomerValidationResult:
        """Validate if customer can operate."""
        ...

    def get_listing_ref(self, customer_ref: str) -> str | None:
        """Return applicable Listing ref."""
        ...

    def get_customer_context(self, ref: str) -> CustomerContext | None:
        """
        Return complete customer context for personalization.

        Used by:
        - LLM for personalized greetings
        - Recommendation system
        - Churn alerts
        """
        ...

    def record_order(self, customer_ref: str, order_data: dict) -> bool:
        """
        Record order in customer history.

        Returns True if recorded successfully.
        """
        ...
