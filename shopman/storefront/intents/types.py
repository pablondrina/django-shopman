"""Storefront intent types."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AddToCartIntent:
    """Domain data for adding one SKU to the cart."""

    sku: str
    qty: int
    unit_price_q: int
    is_d1: bool
    picker_origin: str
    product: object  # Product instance — carried for error-modal rendering


@dataclass
class SetQtyIntent:
    """Domain data for setting an absolute quantity for one SKU."""

    sku: str
    qty: int
    action: str          # "add" | "update" | "remove"
    line_id: str | None  # for "update" / "remove"
    unit_price_q: int    # for "add"
    is_d1: bool          # for "add"
    product: object      # Product instance — carried for error-modal rendering


@dataclass
class CartIntentResult:
    """Result of a cart interpret function.

    On success: ``intent`` is set, ``error_type`` is None.
    On failure: ``intent`` is None, ``error_type`` names the failure,
    ``error_context`` carries context for the view to render the response.
    """

    intent: object | None
    error_type: str | None   # "not_found" | "not_sellable"
    error_context: dict


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
