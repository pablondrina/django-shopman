"""
Loyalty points service.

Core: LoyaltyService (enroll, earn_points, redeem_points)

ASYNC — creates Directive for later processing.
"""

from __future__ import annotations

import logging

from shopman.omniman.models import Directive

logger = logging.getLogger(__name__)

TOPIC = "loyalty.earn"
REDEEM_TOPIC = "loyalty.redeem"


def redeem(order) -> None:
    """
    Schedule loyalty points redemption for the order, if applicable.

    Reads order.data["loyalty"]["redeem_points_q"]. If >0, creates a Directive
    with topic="loyalty.redeem". Handler calls LoyaltyService.redeem_points().

    ASYNC — dispatched on on_commit so points are deducted immediately after order creation.
    """
    redeem_q = (order.data or {}).get("loyalty", {}).get("redeem_points_q", 0)
    if not redeem_q or redeem_q <= 0:
        return

    Directive.objects.create(
        topic=REDEEM_TOPIC,
        payload={
            "order_ref": order.ref,
            "points": int(redeem_q),
        },
    )

    logger.info("loyalty.redeem: queued %d points for order %s", redeem_q, order.ref)


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
