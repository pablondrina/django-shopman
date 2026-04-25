"""Checkout orchestration facade.

This is the single composed checkout path for external surfaces. It resolves
channel configuration, applies checkout/session operations, and commits through
Orderman via ``shopman.shop.services.sessions``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel
from shopman.shop.services import sessions

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckoutResult:
    order_ref: str
    status: str
    total_q: int
    items_count: int


def process(
    session_key: str,
    channel_ref: str,
    data: dict,
    *,
    idempotency_key: str,
    ctx: dict | None = None,
) -> CheckoutResult:
    """Convert checkout data to session operations and commit."""
    customer = data.get("customer") or {}
    phone = customer.get("phone") if isinstance(customer, dict) else ""
    if phone:
        sessions.assign_phone_handle(
            session_key=session_key,
            channel_ref=channel_ref,
            phone=phone,
        )
    return process_ops(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=_build_ops_from_data(data),
        idempotency_key=idempotency_key,
        ctx=ctx,
    )


def process_ops(
    *,
    session_key: str,
    channel_ref: str,
    ops: list[dict],
    idempotency_key: str,
    ctx: dict | None = None,
) -> CheckoutResult:
    """Apply already-built session operations and commit."""
    ctx = ctx or {}
    channel = Channel.objects.get(ref=channel_ref)
    resolved_config = ChannelConfig.for_channel(channel).to_dict()

    if ops:
        sessions.modify_session(
            session_key=session_key,
            channel_ref=channel_ref,
            ops=ops,
            ctx=ctx,
            channel_config=resolved_config,
        )

    commit = sessions.commit_session(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idempotency_key,
        ctx=ctx,
        channel_config=resolved_config,
    )

    logger.info("checkout.process: order %s committed for channel %s", commit.order_ref, channel_ref)
    return CheckoutResult(
        order_ref=commit.order_ref,
        status=commit.status,
        total_q=commit.total_q,
        items_count=commit.items_count,
    )


def _build_ops_from_data(data: dict) -> list[dict]:
    """Convert checkout data dict into Orderman session operations."""
    ops = []
    data_fields = [
        "customer",
        "fulfillment_type",
        "delivery_address",
        "delivery_address_structured",
        "delivery_date",
        "delivery_time_slot",
        "order_notes",
        "payment",
        "loyalty",
        "manual_discount",
        "stock_check_unavailable",
    ]
    for field in data_fields:
        if field in data:
            ops.append({"op": "set_data", "path": field, "value": data[field]})
    return ops
