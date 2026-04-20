"""PaymentProjection — read models for the payment page (Fase 2).

Translates Payman intent state + order.data["payment"] into immutable
projections the v2 payment template and its HTMX polling partial consume.

``build_payment``        → full page (PIX QR code or Stripe card).
``build_payment_status`` → polling partial — checks expiry, paid, cancelled.

Never imports from ``shopman.shop.web.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from shopman.utils.monetary import format_money

if TYPE_CHECKING:
    from shopman.orderman.models import Order

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Dataclasses
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PaymentProjection:
    """Full read model for the payment page.

    Both PIX and card paths share this dataclass; the template branches
    on ``method``. Fields irrelevant to a path carry ``None``.
    """

    order_ref: str
    method: str          # "pix", "card", "cash", "counter"
    total_display: str

    # PIX fields (method == "pix")
    pix_qr_code: str | None       # QR code string for SVG/canvas render
    pix_copy_paste: str | None    # copia-e-cola string
    pix_expires_at: str | None    # ISO datetime string for Alpine countdown

    # Card fields (method == "card")
    # Stripe Checkout (hosted): URL the client is redirected to.
    checkout_url: str | None

    # Polling endpoint (HTMX)
    status_url: str              # URL for hx-get polling partial

    is_debug: bool


@dataclass(frozen=True)
class PaymentStatusProjection:
    """Read model for the HTMX polling partial.

    Views return HTTP 286 when ``is_terminal`` to stop HTMX polling.
    """

    order_ref: str
    is_paid: bool
    is_cancelled: bool
    is_expired: bool
    is_terminal: bool   # paid OR cancelled OR expired (stop polling)
    redirect_url: str   # tracking page — used in HX-Redirect when paid


# ──────────────────────────────────────────────────────────────────────
# Builders
# ──────────────────────────────────────────────────────────────────────


def build_payment(order: Order) -> PaymentProjection:
    """Build the full payment page projection for an Order.

    If the order is already paid or cancelled the view should redirect;
    this builder is only called when payment is genuinely pending.
    """
    from django.conf import settings
    from django.urls import reverse

    payment = order.data.get("payment") or {}
    method = payment.get("method") or "pix"
    total_display = f"R$ {format_money(order.total_q)}"

    # PIX
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

    # Card — Stripe Checkout hosted URL
    checkout_url: str | None = None
    if method == "card":
        checkout_url = payment.get("checkout_url") or None

    status_url = reverse("storefront:payment_status_partial", kwargs={"ref": order.ref})

    return PaymentProjection(
        order_ref=order.ref,
        method=method,
        total_display=total_display,
        pix_qr_code=pix_qr_code,
        pix_copy_paste=pix_copy_paste,
        pix_expires_at=pix_expires_at,
        checkout_url=checkout_url,
        status_url=status_url,
        is_debug=settings.DEBUG,
    )


def build_payment_status(order: Order) -> PaymentStatusProjection:
    """Build the polling partial projection for an Order."""
    from shopman.shop.services import payment as payment_svc

    is_paid = payment_svc.get_payment_status(order) == "captured"
    is_cancelled = order.status == "cancelled"

    is_expired = False
    payment = order.data.get("payment") or {}
    expires_at_str = payment.get("expires_at")
    if expires_at_str and not is_paid and not is_cancelled:
        try:
            from django.utils import timezone
            from django.utils.dateparse import parse_datetime

            expires_at = parse_datetime(expires_at_str)
            if expires_at and timezone.now() > expires_at:
                is_expired = True
        except Exception:
            logger.exception("payment_status_expiry_parse_failed order=%s", order.ref)

    is_terminal = is_paid or is_cancelled or is_expired

    return PaymentStatusProjection(
        order_ref=order.ref,
        is_paid=is_paid,
        is_cancelled=is_cancelled,
        is_expired=is_expired,
        is_terminal=is_terminal,
        redirect_url=f"/pedido/{order.ref}/",
    )


__all__ = [
    "PaymentProjection",
    "PaymentStatusProjection",
    "build_payment",
    "build_payment_status",
]
