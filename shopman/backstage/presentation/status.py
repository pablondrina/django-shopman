"""Backstage status presentation.

Resolves the semantic enums the data Projection carries — order status, payment
method, status ``Tone`` — into the operator-facing display strings and Tailwind
colour tokens.

Copy is authoritative in the orchestrator (``OMOTENASHI_DEFAULTS``); this module
only *places* it via :func:`build_copy`, passing the raw key as a last-resort
fallback. The tone→class map is the backstage's own design-token translation —
rule R-B keeps those classes out of ``shop/projections`` (the data read-side).
"""

from __future__ import annotations

from shopman.shop.projections.copy import build_copy
from shopman.shop.projections.types import ORDER_STATUS_TONES, Tone

# Tone → backstage design-token classes.
_TONE_CLASSES: dict[Tone, str] = {
    Tone.INFO: "bg-info/10 text-info border border-info/20",
    Tone.WARNING: "bg-warning/10 text-warning border border-warning/20",
    Tone.SUCCESS: "bg-success/10 text-success border border-success/20",
    Tone.DANGER: "bg-danger/10 text-danger border border-danger/20",
    Tone.NEUTRAL: "bg-surface-alt text-on-surface/60 border border-outline",
}

# Fallback class for a status with no known tone (operator queue convention).
DEFAULT_STATUS_COLOR = "bg-muted text-muted-foreground"


def status_color(status: str) -> str:
    """Map an order status to its backstage colour-token classes."""
    tone = ORDER_STATUS_TONES.get(status)
    return _TONE_CLASSES[tone] if tone else DEFAULT_STATUS_COLOR


def order_status_label(status: str | None, fallback: str | None = None) -> str:
    """Resolve an order-status key to its display label.

    ``fallback`` defaults to the raw status (or ``""`` for an empty status).
    """
    fb = (status or "") if fallback is None else fallback
    if not status:
        return fb
    return build_copy("ORDER_STATUS").title(f"ORDER_STATUS_{status.upper()}", fb)


def payment_method_label(method: str) -> str:
    """Resolve a payment-method ref to its display label."""
    return build_copy("PAYMENT_METHOD").title(f"PAYMENT_METHOD_{method.upper()}", method)
