"""Intent types for storefront views."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


@dataclass(frozen=True)
class CheckoutIntent:
    """All domain data extracted from a checkout POST.

    Immutable after construction. ``checkout_data`` is the pre-assembled dict
    ready for ``services.checkout.process()``.
    """

    session_key: str
    channel_ref: str
    customer_name: str
    customer_phone: str              # normalized
    fulfillment_type: str            # "pickup" | "delivery"
    payment_method: str
    delivery_address: str | None
    delivery_address_structured: dict | None
    saved_address_id: int | None
    delivery_date: str | None        # "YYYY-MM-DD"
    delivery_time_slot: str | None
    notes: str | None
    loyalty_redeem: bool
    loyalty_balance_q: int
    stock_check_unavailable: bool
    idempotency_key: str
    checkout_data: dict              # assembled for services.checkout.process()


@dataclass
class IntentResult:
    """Result of ``interpret_checkout()``.

    On success: ``intent`` is set, ``errors`` is empty.
    On failure: ``intent`` is None, ``errors`` has user-facing messages.
    ``form_data`` always carries raw POST values for form re-population.
    ``repricing_warnings`` is always populated (may be empty list).
    """

    intent: CheckoutIntent | None
    errors: dict[str, str]
    form_data: dict
    repricing_warnings: list


# ── Auth intents ──────────────────────────────────────────────────────────────

T = TypeVar("T")


@dataclass
class AuthResult(Generic[T]):
    """Result of an auth intent extraction.

    On success: ``intent`` is set, ``errors`` is empty.
    On failure: ``intent`` is None, ``errors`` has user-facing messages.
    ``form_data`` carries raw POST values for template re-population.
    """

    intent: T | None
    errors: dict[str, str]
    form_data: dict


@dataclass(frozen=True)
class LoginIntent:
    step: str               # "phone" | "name"
    phone: str | None       # normalized E.164, set when step="phone"
    delivery_method: str | None  # "whatsapp" | "sms", set when step="phone"
    name: str | None        # set when step="name"
    next_url: str


@dataclass(frozen=True)
class RequestCodeIntent:
    phone: str  # normalized E.164


@dataclass(frozen=True)
class VerifyCodeIntent:
    phone: str  # normalized E.164
    code: str


@dataclass(frozen=True)
class DeviceCheckLoginIntent:
    phone: str  # normalized E.164


@dataclass(frozen=True)
class WelcomeIntent:
    name: str           # cleaned display name
    next_url: str
    customer_uuid: str  # for customer_service.get_by_uuid()
