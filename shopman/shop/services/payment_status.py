"""Canonical payment read models for customer-facing payment surfaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.urls import reverse
from shopman.utils.monetary import format_money

from shopman.shop.services import payment as payment_service

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PaymentReadModel:
    """Canonical full payment page read model."""

    order_ref: str
    method: str
    total_display: str
    pix_qr_code: str | None
    pix_copy_paste: str | None
    pix_expires_at: str | None
    checkout_url: str | None
    status_url: str
    is_debug: bool


@dataclass(frozen=True)
class PaymentStatusReadModel:
    """Canonical payment status polling read model."""

    order_ref: str
    is_paid: bool
    is_cancelled: bool
    is_expired: bool
    is_terminal: bool
    redirect_url: str


def get_payment_status(order) -> str | None:
    """Return payment status from Payman via the payment service."""
    return payment_service.get_payment_status(order)


def can_cancel(order) -> bool:
    return payment_service.can_cancel(order)


def build_payment(order, *, is_debug: bool = False) -> PaymentReadModel:
    """Build payment page data from order payment display metadata."""
    payment = (order.data or {}).get("payment") or {}
    method = payment.get("method") or "pix"

    pix_qr_code: str | None = None
    pix_copy_paste: str | None = None
    pix_expires_at: str | None = None
    if method == "pix":
        pix_qr_code = payment.get("qr_code") or payment.get("pix_qr_code") or None
        pix_copy_paste = (
            payment.get("copy_paste")
            or payment.get("pix_copy_paste")
            or payment.get("pix_code")
            or None
        )
        pix_expires_at = payment.get("expires_at") or None

    checkout_url: str | None = None
    if method == "card":
        checkout_url = payment.get("checkout_url") or None

    return PaymentReadModel(
        order_ref=order.ref,
        method=method,
        total_display=f"R$ {format_money(order.total_q)}",
        pix_qr_code=pix_qr_code,
        pix_copy_paste=pix_copy_paste,
        pix_expires_at=pix_expires_at,
        checkout_url=checkout_url,
        status_url=reverse("storefront:payment_status_partial", kwargs={"ref": order.ref}),
        is_debug=is_debug,
    )


def build_payment_status(order) -> PaymentStatusReadModel:
    """Build payment polling state, degrading malformed expiry to non-expired."""
    is_paid = get_payment_status(order) == "captured"
    is_cancelled = order.status == "cancelled"

    is_expired = False
    payment = (order.data or {}).get("payment") or {}
    expires_at_str = payment.get("expires_at")
    if expires_at_str and not is_paid and not is_cancelled:
        try:
            from django.utils import timezone
            from django.utils.dateparse import parse_datetime

            expires_at = parse_datetime(expires_at_str)
            if expires_at and timezone.now() > expires_at:
                is_expired = True
        except Exception:
            logger.warning("payment_status_expiry_parse_failed order=%s", order.ref, exc_info=True)

    return PaymentStatusReadModel(
        order_ref=order.ref,
        is_paid=is_paid,
        is_cancelled=is_cancelled,
        is_expired=is_expired,
        is_terminal=is_paid or is_cancelled or is_expired,
        redirect_url=f"/pedido/{order.ref}/",
    )


__all__ = [
    "PaymentReadModel",
    "PaymentStatusReadModel",
    "build_payment",
    "build_payment_status",
    "can_cancel",
    "get_payment_status",
]
