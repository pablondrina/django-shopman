"""Payment projections consumed by storefront templates."""

from __future__ import annotations

from shopman.shop.services.payment_status import (
    PaymentProjection,
    PaymentPromiseProjection,
    PaymentStatusProjection,
)
from shopman.shop.services.payment_status import (
    build_payment as build_payment_projection,
)
from shopman.shop.services.payment_status import (
    build_payment_status as build_payment_status_projection,
)


def build_payment(order) -> PaymentProjection:
    """Build the full payment page projection for an Order."""
    from django.conf import settings

    return build_payment_projection(order, is_debug=settings.DEBUG)


def build_payment_status(order) -> PaymentStatusProjection:
    """Build the polling partial projection for an Order."""
    return build_payment_status_projection(order)


__all__ = [
    "PaymentProjection",
    "PaymentPromiseProjection",
    "PaymentStatusProjection",
    "build_payment",
    "build_payment_status",
]
