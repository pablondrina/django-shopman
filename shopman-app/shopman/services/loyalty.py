"""
Loyalty points service.

Core: LoyaltyService (enroll, earn_points)

ASYNC — creates Directive for later processing.
"""

from __future__ import annotations

import logging

from shopman.ordering.models import Directive

logger = logging.getLogger(__name__)

TOPIC = "loyalty.earn"


def earn(order) -> None:
    """
    Schedule loyalty points earning for the order.

    Creates a Directive with topic="loyalty.earn". The handler that
    processes the Directive finds the customer, calculates points
    (1 point per R$1), and calls LoyaltyService.earn_points().

    ASYNC — non-critical, can fail without impacting the order.
    """
    if not order.total_q or order.total_q <= 0:
        return

    Directive.objects.create(
        topic=TOPIC,
        payload={
            "order_ref": order.ref,
        },
    )

    logger.info("loyalty.earn: queued for order %s", order.ref)
