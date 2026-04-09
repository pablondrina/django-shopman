"""
Shared helpers for reading canonical order data fields.

These helpers centralise fallback logic for fields that were renamed
during the session→order data schema evolution.
"""

from __future__ import annotations


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
