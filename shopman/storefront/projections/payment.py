"""PaymentProjection — read models for the payment page (Fase 2).

Translates Payman intent state + order.data["payment"] into immutable
projections the payment template and its HTMX polling partial consume.

``build_payment``        → full page (PIX QR code or Stripe card).
``build_payment_status`` → polling partial — checks expiry, paid, cancelled.

Never imports from ``shopman.storefront.views.*``.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    method: str          # "pix", "card", "cash", "external"
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


def build_payment(order) -> PaymentProjection:
    """Build the full payment page projection for an Order.

    If the order is already paid or cancelled the view should redirect;
    this builder is only called when payment is genuinely pending.
    """
    from django.conf import settings

    from shopman.shop.services import payment_status

    read_model = payment_status.build_payment(order, is_debug=settings.DEBUG)
    return PaymentProjection(
        order_ref=read_model.order_ref,
        method=read_model.method,
        total_display=read_model.total_display,
        pix_qr_code=read_model.pix_qr_code,
        pix_copy_paste=read_model.pix_copy_paste,
        pix_expires_at=read_model.pix_expires_at,
        checkout_url=read_model.checkout_url,
        status_url=read_model.status_url,
        is_debug=read_model.is_debug,
    )


def build_payment_status(order) -> PaymentStatusProjection:
    """Build the polling partial projection for an Order."""
    from shopman.shop.services import payment_status

    read_model = payment_status.build_payment_status(order)
    return PaymentStatusProjection(
        order_ref=read_model.order_ref,
        is_paid=read_model.is_paid,
        is_cancelled=read_model.is_cancelled,
        is_expired=read_model.is_expired,
        is_terminal=read_model.is_terminal,
        redirect_url=read_model.redirect_url,
    )


__all__ = [
    "PaymentProjection",
    "PaymentStatusProjection",
    "build_payment",
    "build_payment_status",
]
