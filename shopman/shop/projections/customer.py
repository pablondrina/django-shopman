"""Customer — read-side Projection of data (order history summaries).

The policy-laden, semantic read model for a customer's order list. It resolves
the identity filter and emits compact order summaries as **data**: refs, raw
timestamps, ``_q`` cents, status keys and counts. It carries **no** status
label, colour token or money formatting — those are Presentation, resolved per
surface in ``storefront/presentation/{order_history,account}.py``.

Identity resolution and the active-status set are policy primitives owned by the
write-side facade (``shop.services.customer_orders``, consumed by the spine for
access/counts); this module imports them so there is one identity contract.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from shopman.shop.services.customer_orders import (
    ACTIVE_STATUSES,
    customer_identity_filter,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CustomerOrderSummary:
    """Canonical compact order summary — semantic, prices in cents.

    Carries the status *key* (``status``); the label and colour are resolved by
    Presentation. ``created_at`` is the raw timestamp (Presentation formats it).
    """

    ref: str
    created_at: Any
    total_q: int
    status: str
    item_count: int


def history_summaries_for_customer(
    *,
    customer_ref: str | None = None,
    phone: str | None = None,
    filter_param: str = "todos",
    limit: int = 50,
) -> tuple[CustomerOrderSummary, ...]:
    """Return order summaries for one authenticated customer identity.

    ``customer_ref`` is the canonical sealed link. ``phone`` is accepted as the
    external handle for orders that entered through phone-based surfaces, so
    history, account, badges, loyalty and quick reorder do not contradict each
    other when the same customer is resolved from different entry points.
    """
    try:
        from shopman.orderman.models import Order

        identity = customer_identity_filter(customer_ref=customer_ref, phone=phone)
        if identity is None:
            return ()

        qs = Order.objects.filter(identity).distinct().order_by("-created_at")
        qs = _apply_history_filter(qs, filter_param)
        return _summaries_from_orders(qs[:limit])
    except Exception:
        logger.warning(
            "customer_order_history_failed customer_ref=%s phone=%s",
            customer_ref,
            phone,
            exc_info=True,
        )
        return ()


def history_summaries_for_phone(
    phone: str,
    *,
    filter_param: str = "todos",
    limit: int = 50,
) -> tuple[CustomerOrderSummary, ...]:
    """Return canonical order summaries for a phone, degrading to an empty tuple."""
    return history_summaries_for_customer(
        phone=phone,
        filter_param=filter_param,
        limit=limit,
    )


def history_summaries_for_customer_ref(
    customer_ref: str,
    *,
    limit: int = 10,
) -> tuple[CustomerOrderSummary, ...]:
    """Return canonical order summaries for a customer ref."""
    return history_summaries_for_customer(customer_ref=customer_ref, limit=limit)


def _apply_history_filter(qs, filter_param: str):
    if filter_param == "ativos":
        return qs.filter(status__in=ACTIVE_STATUSES)
    if filter_param == "anteriores":
        return qs.exclude(status__in=ACTIVE_STATUSES)
    return qs


def _summaries_from_orders(orders) -> tuple[CustomerOrderSummary, ...]:
    return tuple(
        CustomerOrderSummary(
            ref=order.ref,
            created_at=order.created_at,
            total_q=order.total_q,
            status=order.status,
            item_count=order.items.count(),
        )
        for order in orders
    )


__all__ = [
    "CustomerOrderSummary",
    "history_summaries_for_customer",
    "history_summaries_for_customer_ref",
    "history_summaries_for_phone",
]
