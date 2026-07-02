"""
Loyalty points service.

Core: LoyaltyService (enroll, earn_points, redeem_points)

ASYNC — creates Directive for later processing.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive

logger = logging.getLogger(__name__)

TOPIC = "loyalty.earn"
REDEEM_TOPIC = "loyalty.redeem"


def redeem(order) -> None:
    """
    Schedule loyalty points redemption for the order, if applicable.

    Reads order.data["loyalty"]["applied_discount_q"] — o desconto efetivamente
    aplicado pelo LoyaltyRedeemModifier (clampado ao subtotal), nunca o saldo
    pedido. If >0, creates a Directive with topic="loyalty.redeem".

    ASYNC — dispatched on on_commit so points are deducted immediately after order creation.
    """
    applied_q = int((order.data or {}).get("loyalty", {}).get("applied_discount_q") or 0)
    if applied_q <= 0:
        return

    Directive.objects.create(
        topic=REDEEM_TOPIC,
        payload={
            "order_ref": order.ref,
            "points": applied_q,
        },
    )

    logger.info("loyalty.redeem: queued %d points for order %s", applied_q, order.ref)


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
