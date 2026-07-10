"""Courier dispatch handler — abre a corrida na Machine (Directive ``courier.dispatch``).

Enfileirado por ``courier.request_dispatch`` quando um pedido delivery fica
pronto (lifecycle ``on_ready`` com ``fulfillment.courier="auto"``) ou pelo
re-despacho manual do operador no gestor. Retry/idempotência vêm da Directive
(ADR-003): falha de rede re-agenda; replay com corrida ativa é no-op.
"""

from __future__ import annotations

import logging

from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive, Order

from shopman.shop.directives import COURIER_DISPATCH

logger = logging.getLogger(__name__)


class CourierDispatchHandler:
    """Abre a solicitação de entrega no adapter courier e grava a corrida no pedido."""

    topic = COURIER_DISPATCH

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from django.utils import timezone

        from shopman.shop.adapters import get_adapter
        from shopman.shop.adapters.courier_machine import CourierError
        from shopman.shop.services import courier
        from shopman.shop.services.order_helpers import get_fulfillment_type

        payload = message.payload or {}
        try:
            order = Order.objects.get(ref=payload["order_ref"])
        except (KeyError, Order.DoesNotExist):
            return

        # Revalidação: o mundo pode ter mudado entre a fila e a execução.
        if get_fulfillment_type(order) != "delivery":
            return
        if order.status not in (Order.Status.READY, Order.Status.DISPATCHED):
            logger.info(
                "courier.dispatch_skipped order=%s status=%s", order.ref, order.status
            )
            return
        if courier.has_active_ride(order):
            return  # replay at-least-once: corrida já aberta

        adapter = get_adapter("courier")
        if adapter is None:
            return

        # Cotação best-effort (custo interno exibido no gestor) — nunca bloqueia.
        courier.estimate_for_order(order, store=True)

        try:
            result = adapter.dispatch(courier.build_machine_payload(order))
        except CourierError as exc:
            if exc.transient:
                raise DirectiveTransientError(str(exc)) from exc
            self._record_terminal_failure(order, str(exc))
            raise DirectiveTerminalError(str(exc)) from exc
        except ValueError as exc:
            # Payload impossível (pedido sem endereço, loja sem partida) — dado,
            # não rede: re-tentar não resolve.
            self._record_terminal_failure(order, str(exc))
            raise DirectiveTerminalError(str(exc)) from exc

        if result.inert:
            logger.info("courier.dispatch_inert order=%s (trava dev/seed)", order.ref)
            return

        block = courier.get_block(order)
        block.update(
            {
                "provider": "machine",
                "id_mch": result.courier_ref,
                "status": "D",
                "requested_at": timezone.now().isoformat(),
                "last_event_at": timezone.now().isoformat(),
                "last_source": "dispatch",
            }
        )
        block.pop("error", None)
        courier._save_block(order, block, emit={"kind": "dispatched", "status": "D"})
        order.emit_event(
            event_type="courier_ride_opened",
            actor=str(payload.get("actor") or "courier.dispatch"),
            payload={"id_mch": result.courier_ref},
        )
        logger.info("courier.ride_opened order=%s id_mch=%s", order.ref, result.courier_ref)

        seconds = courier.poll_seconds()
        if seconds > 0:
            courier.schedule_sync(order, delay_seconds=min(seconds, courier.FIRST_SYNC_SECONDS))

    @staticmethod
    def _record_terminal_failure(order, message: str) -> None:
        from django.utils import timezone

        from shopman.shop.adapters import alert as alert_adapter
        from shopman.shop.services import courier

        block = courier.get_block(order)
        block["error"] = {"message": message[:500], "at": timezone.now().isoformat()}
        courier._save_block(order, block, emit={"kind": "dispatch_failed"})
        try:
            alert_adapter.create(
                "courier_dispatch_failed",
                "critical",
                f"Falha ao abrir corrida do pedido {order.ref}: {message[:200]}",
                order_ref=order.ref,
            )
        except Exception:
            logger.warning("courier.alert_failed order=%s", order.ref, exc_info=True)


__all__ = ["CourierDispatchHandler"]
