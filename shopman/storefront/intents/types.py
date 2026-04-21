"""Checkout intent types."""

from __future__ import annotations

from dataclasses import dataclass


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
