"""
Fulfillment handlers — criação e atualização de fulfillment.

FulfillmentCreateHandler: cria registro após confirmação. Delega para services.fulfillment.create().
FulfillmentUpdateHandler: transições, tracking, auto-sync com Order. Delega para services.fulfillment.update().
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive

from shopman.shop.directives import FULFILLMENT_CREATE, FULFILLMENT_UPDATE, NOTIFICATION_SEND

logger = logging.getLogger(__name__)


class FulfillmentCreateHandler:
    """
    Cria registro de fulfillment após confirmação do pedido.

    Topic: fulfillment.create
    Payload: {order_ref, channel_ref}

    Idempotente via services.fulfillment.create().
    """

    topic = FULFILLMENT_CREATE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.models import Order

        from shopman.shop.services import fulfillment as fulfillment_svc

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

        fulfillment_svc.create(order)

        logger.info("FulfillmentCreateHandler: created fulfillment for %s", order_ref)
        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


class FulfillmentUpdateHandler:
    """
    Atualiza status de fulfillment com tracking e auto-sync.

    Topic: fulfillment.update
    Payload: {order_ref, fulfillment_id, new_status, tracking_code?, carrier?}

    - Delega update para services.fulfillment.update()
    - Auto-sync com Order status (se config.fulfillment.auto_sync)
    - Cria notificações para DISPATCHED e DELIVERED
    """

    topic = FULFILLMENT_UPDATE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.orderman.exceptions import InvalidTransition
        from shopman.orderman.models import Fulfillment, Order

        from shopman.shop.config import ChannelConfig
        from shopman.shop.services import fulfillment as fulfillment_svc

        payload = message.payload
        order_ref = payload.get("order_ref")
        fulfillment_id = payload.get("fulfillment_id")
        new_status = payload.get("new_status")

        if not order_ref:
            message.status = "failed"
            message.last_error = "missing order_ref"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if not fulfillment_id:
            message.status = "failed"
            message.last_error = "missing fulfillment_id"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        if not new_status:
            message.status = "failed"
            message.last_error = "missing new_status"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        try:
            order = Order.objects.get(ref=order_ref)
        except Order.DoesNotExist:
            message.status = "failed"
            message.last_error = f"Order not found: {order_ref}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        try:
            fulfillment = Fulfillment.objects.get(pk=fulfillment_id, order=order)
        except Fulfillment.DoesNotExist:
            message.status = "failed"
            message.last_error = f"Fulfillment not found: {fulfillment_id}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Idempotência: já no status alvo
        if fulfillment.status == new_status:
            logger.info(
                "FulfillmentUpdateHandler: fulfillment %s already at %s",
                fulfillment_id,
                new_status,
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        tracking_code = payload.get("tracking_code")
        carrier = payload.get("carrier")

        try:
            fulfillment_svc.update(fulfillment, new_status, tracking_code, carrier)
        except InvalidTransition as exc:
            message.status = "failed"
            message.last_error = str(exc)
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        logger.info(
            "FulfillmentUpdateHandler: fulfillment %s → %s for order %s",
            fulfillment_id,
            new_status,
            order_ref,
        )

        # Auto-sync com Order
        config = ChannelConfig.for_channel(order.channel_ref)
        if config.fulfillment.auto_sync:
            self._sync_order_status(order, new_status)

        # Notificações por transição
        self._create_notifications(order, fulfillment, new_status)

        message.status = "done"
        message.save(update_fields=["status", "updated_at"])

    def _sync_order_status(self, order, fulfillment_status: str) -> None:
        """Auto-sync: fulfillment status → order status."""
        from shopman.orderman.models import Order

        sync_map = {
            "dispatched": Order.Status.DISPATCHED,
            "delivered": Order.Status.DELIVERED,
        }

        target = sync_map.get(fulfillment_status)
        if target and order.can_transition_to(target):
            order.transition_status(target, actor="fulfillment.sync")
            logger.info(
                "FulfillmentUpdateHandler: synced order %s → %s",
                order.ref,
                target,
            )

    def _create_notifications(self, order, fulfillment, new_status: str) -> None:
        """Cria directives de notificação para transições relevantes."""
        template_map = {
            "dispatched": "order_dispatched",
            "delivered": "order_delivered",
        }

        template = template_map.get(new_status)
        if not template:
            return

        payload = {
            "order_ref": order.ref,
            "channel_ref": order.channel_ref,
            "template": template,
        }

        # Enriquecer com tracking info para DISPATCHED
        if new_status == "dispatched":
            tracking = {}
            if fulfillment.tracking_code:
                tracking["tracking_code"] = fulfillment.tracking_code
            if fulfillment.tracking_url:
                tracking["tracking_url"] = fulfillment.tracking_url
            if fulfillment.carrier:
                tracking["carrier"] = fulfillment.carrier
            if tracking:
                payload["tracking"] = tracking

        Directive.objects.create(topic=NOTIFICATION_SEND, payload=payload)
