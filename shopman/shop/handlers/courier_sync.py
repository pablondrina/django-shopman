"""Courier sync handler — polling do status da corrida (Directive ``courier.sync``).

Fallback do webhook da Machine (e única via enquanto o webhook não estiver
homologado): heartbeat auto-reagendável por pedido, no padrão do
``production.late_check``. Para sozinho quando a corrida chega a um status
terminal (F/N/C), quando a corrida some do pedido, ou quando o polling é
desligado (``Shop.defaults.delivery.courier_poll_seconds = 0``).

Webhook e polling convergem no mesmo funil (``courier.apply_status``), que é
idempotente — receber o mesmo status pelas duas vias é inofensivo.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Directive, Order

from shopman.shop.directives import COURIER_SYNC

logger = logging.getLogger(__name__)


class CourierSyncHandler:
    """Consulta o status da corrida no adapter e aplica ao pedido."""

    topic = COURIER_SYNC

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.adapters import get_adapter
        from shopman.shop.adapters.courier_machine import TERMINAL_STATUSES, CourierError
        from shopman.shop.services import courier

        payload = message.payload or {}
        try:
            order = Order.objects.get(ref=payload["order_ref"])
        except (KeyError, Order.DoesNotExist):
            return

        block = courier.get_block(order)
        if not block.get("id_mch") or block.get("status") in TERMINAL_STATUSES:
            return  # corrida encerrada/removida — heartbeat morre aqui

        adapter = get_adapter("courier")
        if adapter is None:
            return

        seconds = courier.poll_seconds()

        try:
            status = adapter.get_status(block["id_mch"])
        except CourierError as exc:
            # Transient ou não, o heartbeat não "falha": loga e re-agenda — a
            # próxima batida (ou o webhook) recupera o estado.
            logger.warning(
                "courier.sync_failed order=%s id_mch=%s: %s",
                order.ref, block.get("id_mch"), exc,
            )
            if seconds > 0:
                courier.schedule_sync(order, delay_seconds=seconds)
            return

        if status:
            courier.apply_status(order, status, source="poll")

        block = courier.get_block(order)
        still_active = bool(block.get("id_mch")) and block.get("status") not in TERMINAL_STATUSES
        if still_active and seconds > 0:
            courier.schedule_sync(order, delay_seconds=seconds)


__all__ = ["CourierSyncHandler"]
