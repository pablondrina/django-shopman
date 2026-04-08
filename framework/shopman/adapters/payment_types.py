"""
Canonical DTOs for payment adapter contracts.

All payment adapters (mock, stripe, efi) MUST return these dataclasses from
their public functions. The orchestrating service (shopman.services.payment)
consumes them by attribute access — no dict lookups, no `.get()`.

This is the contract between framework/shopman/services/payment.py and the
adapter modules in framework/shopman/adapters/payment_*.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PaymentIntent:
    """Result of `adapter.create_intent()`.

    `intent_ref` is the canonical id, aligned with `payman.PaymentService.ref`
    (the DB row ref). The orchestrator persists this in
    `order.data["payment"]["intent_ref"]`.
    """

    intent_ref: str
    status: str  # "pending" | "authorized" | "requires_action" | "captured" | ...
    amount_q: int
    currency: str = "BRL"
    client_secret: str | None = None
    expires_at: datetime | None = None
    gateway_id: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PaymentResult:
    """Result of `adapter.capture()`, `refund()`, `cancel()`.

    `success=False` carries `error_code` + `message`. On success, `transaction_id`
    is the gateway-side identifier (e.g. Stripe charge id, EFI e2e id).
    """

    success: bool
    transaction_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None
