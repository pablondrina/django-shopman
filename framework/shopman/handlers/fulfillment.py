"""
Fulfillment handlers — criação e atualização de fulfillment.

FulfillmentCreateHandler: cria registro após confirmação.
FulfillmentUpdateHandler: transições, tracking, auto-sync com Order.
"""

from __future__ import annotations

import logging

from shopman.omniman.models import Directive
from shopman.topics import FULFILLMENT_CREATE, FULFILLMENT_UPDATE, NOTIFICATION_SEND

logger = logging.getLogger(__name__)

# ── Tracking URL patterns para transportadoras conhecidas ──

CARRIER_TRACKING_URLS = {
    "correios": "https://rastreamento.correios.com.br/app/index.php?objetos={code}",
    "sedex": "https://rastreamento.correios.com.br/app/index.php?objetos={code}",
    "jadlog": "https://www.jadlog.com.br/tracking?code={code}",
    "loggi": "https://www.loggi.com/rastreio/{code}",
}


def _enrich_tracking_url(carrier: str, tracking_code: str) -> str:
    """Gera tracking URL automaticamente quando carrier é conhecido."""
    pattern = CARRIER_TRACKING_URLS.get(carrier.lower())
    if pattern and tracking_code:
        return pattern.format(code=tracking_code)
    return ""


class FulfillmentCreateHandler:
    """
    Cria registro de fulfillment após confirmação do pedido.

    Topic: fulfillment.create
    Payload: {order_ref, channel_ref}

    Idempotente: verifica se fulfillment já existe antes de criar.
    """

    topic = FULFILLMENT_CREATE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.omniman.models import Order

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

        # Idempotência: não criar duas vezes
        if order.data.get("fulfillment_created"):
            logger.info(
                "FulfillmentCreateHandler: fulfillment already exists for %s",
                order_ref,
            )
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        order.data["fulfillment_created"] = True
        order.save(update_fields=["data", "updated_at"])

        logger.info("FulfillmentCreateHandler: created fulfillment for %s", order_ref)
        message.status = "done"
        message.save(update_fields=["status", "updated_at"])


class FulfillmentUpdateHandler:
    """
    Atualiza status de fulfillment com tracking e auto-sync.

    Topic: fulfillment.update
    Payload: {order_ref, fulfillment_id, new_status, tracking_code?, carrier?}

    - Executa transição no Fulfillment model
    - Auto-seta tracking_url quando carrier é conhecido
    - Auto-sync com Order status (se config.flow.auto_sync_fulfillment)
    - Cria notificações para DISPATCHED e DELIVERED
    """

    topic = FULFILLMENT_UPDATE

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.config import ChannelConfig
        from shopman.omniman.exceptions import InvalidTransition
        from shopman.omniman.models import Fulfillment, Order

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

        # Atualizar tracking info se fornecido
        tracking_code = payload.get("tracking_code")
        carrier = payload.get("carrier")

        if tracking_code:
            fulfillment.tracking_code = tracking_code
        if carrier:
            fulfillment.carrier = carrier

        # Auto-enrich tracking URL
        effective_carrier = carrier or fulfillment.carrier
        effective_code = tracking_code or fulfillment.tracking_code
        if effective_carrier and effective_code and not fulfillment.tracking_url:
            fulfillment.tracking_url = _enrich_tracking_url(effective_carrier, effective_code)

        # Executar transição
        fulfillment.status = new_status
        try:
            fulfillment.save()
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
        config = ChannelConfig.effective(order.channel)
        if config.flow.auto_sync_fulfillment:
            self._sync_order_status(order, new_status)

        # Notificações por transição
        self._create_notifications(order, fulfillment, new_status)

        message.status = "done"
        message.save(update_fields=["status", "updated_at"])

    def _sync_order_status(self, order, fulfillment_status: str) -> None:
        """Auto-sync: fulfillment status → order status."""
        from shopman.omniman.models import Order

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
            "channel_ref": order.channel.ref,
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
