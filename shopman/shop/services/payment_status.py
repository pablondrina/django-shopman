"""Payment policy facade — write-side, surface-agnostic.

The thin policy seam over Payman used by the spine (lifecycle, handlers,
cancellation) and by the read-side projections. It answers *policy* questions
only — captured-payment sufficiency, live status, cancellability — never shapes
a payment page. The payment page read-model lives in
``shop.projections.payment_status`` (data) and ``storefront.presentation.payment``
(appearance).
"""

from __future__ import annotations

from shopman.shop.services import payment as payment_service


def get_payment_status(order) -> str | None:
    """Return payment status from Payman via the payment service."""
    return payment_service.get_payment_status(order)


def has_sufficient_captured_payment(order) -> bool:
    """Return whether captured funds still cover the order total."""
    return payment_service.has_sufficient_captured_payment(order) is True


def can_cancel(order) -> bool:
    return payment_service.can_cancel(order)


__all__ = [
    "can_cancel",
    "get_payment_status",
    "has_sufficient_captured_payment",
]
