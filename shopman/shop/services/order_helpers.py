"""
Shared helpers for reading canonical order data fields.

These helpers centralise fallback logic for fields that were renamed
during the session→order data schema evolution.
"""

from __future__ import annotations

from datetime import date


def get_fulfillment_type(order) -> str:
    """Return the order's fulfillment type.

    Uses the canonical ``fulfillment_type`` key with a fallback to the
    legacy ``delivery_method`` key so both old and new orders work.

    Returns an empty string when neither key is present.
    """
    return (
        (order.data or {}).get("fulfillment_type")
        or (order.data or {}).get("delivery_method", "")
    )


def parse_commitment_date(value) -> date | None:
    """Parse an ISO delivery date into a ``date`` object."""
    if isinstance(value, date):
        return value
    if not value:
        return None
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def get_commitment_date(source) -> date | None:
    """Return the committed fulfillment date from an order/session/data dict."""
    if source is None:
        return None

    if isinstance(source, dict):
        data = source
    else:
        data = getattr(source, "data", None) or {}

    return parse_commitment_date(data.get("delivery_date"))
