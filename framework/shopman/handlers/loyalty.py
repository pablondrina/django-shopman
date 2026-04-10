"""
Loyalty handlers — earn points on completion, redeem points on commit.
"""

from __future__ import annotations

import logging

from shopman.adapters import get_adapter
from shopman.directives import LOYALTY_EARN, LOYALTY_REDEEM
from shopman.orderman.models import Directive

logger = logging.getLogger(__name__)


class LoyaltyEarnHandler:
    """Awards loyalty points on order completion. Topic: loyalty.earn"""

    topic = LOYALTY_EARN

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")

        if not order_ref:
            message.status = "failed"
            message.last_error = "missing order_ref"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = f"Order not found: {order_ref}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Need a customer handle to find the customer
        if not order.handle_ref:
            logger.debug("loyalty.earn: no handle_ref on order %s, skipping", order_ref)
            message.status = "completed"
            message.save(update_fields=["status", "updated_at"])
            return

        # Find customer by phone
        try:
            adapter = get_adapter("customer")
            customer = adapter.get_customer_by_phone(order.handle_ref)
        except Exception:
            customer = None

        if not customer:
            logger.debug("loyalty.earn: no customer for handle_ref=%s, skipping", order.handle_ref)
            message.status = "completed"
            message.save(update_fields=["status", "updated_at"])
            return

        # Calculate points: 1 point per R$ 1,00 (100 centavos)
        points = order.total_q // 100
        if points <= 0:
            message.status = "completed"
            message.save(update_fields=["status", "updated_at"])
            return

        try:
            # Enroll if not yet enrolled (idempotent)
            adapter.enroll_loyalty(customer["ref"])

            # Award points
            adapter.earn_points(
                customer_ref=customer["ref"],
                points=points,
                description=f"Pedido {order.ref}",
                reference=f"order:{order.ref}",
                created_by="system",
            )

            logger.info("loyalty.earn: +%d points for %s (order %s)", points, customer["ref"], order_ref)

            message.status = "completed"
            message.save(update_fields=["status", "updated_at"])

        except Exception:
            logger.exception("loyalty.earn: failed for order %s", order_ref)
            attempts = (message.attempts or 0) + 1
            message.attempts = attempts
            if attempts >= 3:
                message.status = "failed"
                message.last_error = "max retries exceeded"
            else:
                message.status = "queued"
            message.save(update_fields=["status", "last_error", "attempts", "updated_at"])


class LoyaltyRedeemHandler:
    """Redeems loyalty points on order commit. Topic: loyalty.redeem"""

    topic = LOYALTY_REDEEM

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload
        order_ref = payload.get("order_ref")
        points = int(payload.get("points", 0))

        if not order_ref or points <= 0:
            message.status = "completed"
            message.save(update_fields=["status", "updated_at"])
            return

        try:
            from shopman.orderman.models import Order
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = f"Order not found: {order_ref}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if not order.handle_ref:
            logger.debug("loyalty.redeem: no handle_ref on order %s, skipping", order_ref)
            message.status = "completed"
            message.save(update_fields=["status", "updated_at"])
            return

        try:
            adapter = get_adapter("customer")
            customer = adapter.get_customer_by_phone(order.handle_ref)
        except Exception:
            customer = None

        if not customer:
            logger.debug("loyalty.redeem: no customer for handle_ref=%s, skipping", order.handle_ref)
            message.status = "completed"
            message.save(update_fields=["status", "updated_at"])
            return

        try:
            adapter.redeem_points(
                customer_ref=customer["ref"],
                points=points,
                description=f"Resgate pedido {order_ref}",
                reference=f"order:{order_ref}",
                created_by="system",
            )

            logger.info("loyalty.redeem: -%d points for %s (order %s)", points, customer["ref"], order_ref)

            message.status = "completed"
            message.save(update_fields=["status", "updated_at"])

        except Exception:
            logger.exception("loyalty.redeem: failed for order %s", order_ref)
            attempts = (message.attempts or 0) + 1
            message.attempts = attempts
            if attempts >= 3:
                message.status = "failed"
                message.last_error = "max retries exceeded"
            else:
                message.status = "queued"
            message.save(update_fields=["status", "last_error", "attempts", "updated_at"])
