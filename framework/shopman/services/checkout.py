"""
Checkout processing service.

Core: ModifyService, CommitService
"""

from __future__ import annotations

import logging

from shopman.ordering.services.commit import CommitService
from shopman.ordering.services.modify import ModifyService

logger = logging.getLogger(__name__)


def process(session_key: str, channel_ref: str, data: dict, *, idempotency_key: str, ctx: dict | None = None) -> dict:
    """
    Process a checkout: validate, apply data, and commit.

    Pipeline:
    1. Apply checkout data to session (fulfillment_type, address, etc.) via ModifyService
    2. Commit the session via CommitService → creates Order

    Args:
        session_key: The session key.
        channel_ref: The channel ref.
        data: Checkout data (fulfillment_type, delivery_address, payment method, etc.)
        idempotency_key: Idempotency key for the commit.
        ctx: Additional context.

    Returns:
        dict with order_ref and commit result.

    SYNC — called from the checkout view.
    """
    ctx = ctx or {}

    # 1. Apply checkout data to the session
    ops = _build_ops_from_data(data)
    if ops:
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=channel_ref,
            ops=ops,
            ctx=ctx,
        )

    # 2. Commit
    result = CommitService.commit(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idempotency_key,
        ctx=ctx,
    )

    logger.info("checkout.process: order %s committed", result.get("order_ref"))
    return result


def _build_ops_from_data(data: dict) -> list[dict]:
    """Convert checkout data dict into ModifyService ops."""
    ops = []

    # Standard checkout fields stored in session.data
    data_fields = [
        "customer", "fulfillment_type", "delivery_address",
        "delivery_address_structured", "delivery_date",
        "delivery_time_slot", "order_notes",
        "payment",
        "loyalty",
    ]

    for field in data_fields:
        if field in data:
            ops.append({
                "op": "set_data",
                "path": field,
                "value": data[field],
            })

    return ops
