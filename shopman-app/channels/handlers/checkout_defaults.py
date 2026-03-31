"""
Checkout defaults inference handler — infere defaults pós-commit.

Roda após customer.ensure no pipeline on_commit dos canais remotos.
Analisa histórico de pedidos do cliente no canal e grava preferences inferidas.
"""

from __future__ import annotations

import logging

from shopman.ordering.models import Directive

from channels.topics import CHECKOUT_INFER_DEFAULTS

logger = logging.getLogger(__name__)


class CheckoutInferDefaultsHandler:
    """Infere checkout defaults do histórico. Topic: checkout.infer_defaults"""

    topic = CHECKOUT_INFER_DEFAULTS

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.ordering.models import Order

        payload = message.payload
        order_ref = payload.get("order_ref")

        if not order_ref:
            message.status = "failed"
            message.last_error = "missing order_ref"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        try:
            order = Order.objects.select_related("channel").get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = f"Order not found: {order_ref}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Resolve customer from order data
        customer_ref = (order.data or {}).get("customer_ref")
        if not customer_ref:
            # customer.ensure may not have run yet — skip silently
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        channel_ref = order.channel.ref if order.channel else ""
        if not channel_ref:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        try:
            # Get recent orders for this customer in this channel
            recent_orders = list(
                Order.objects.filter(
                    channel=order.channel,
                    data__customer_ref=customer_ref,
                )
                .exclude(status__in=("cancelled", "returned"))
                .order_by("-created_at")[:10]
            )

            from channels.backends.checkout_defaults import CheckoutDefaultsService

            inferred = CheckoutDefaultsService.infer_from_history(
                customer_ref=customer_ref,
                channel_ref=channel_ref,
                orders=recent_orders,
            )

            if inferred:
                logger.info(
                    "checkout.infer_defaults: inferred %s for %s on channel %s",
                    list(inferred.keys()),
                    customer_ref,
                    channel_ref,
                )

        except Exception as exc:
            logger.warning(
                "checkout.infer_defaults: failed for order %s: %s",
                order_ref,
                exc,
            )

        message.status = "done"
        message.save(update_fields=["status", "updated_at"])
