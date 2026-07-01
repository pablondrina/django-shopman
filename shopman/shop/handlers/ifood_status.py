"""iFood status callback handler + signal receiver (WP-4).

When an iFood-channel order changes status, we must tell iFood. This uses the
same durable pattern as catalog projection: a signal receiver enqueues a
``ifood.status_callback`` Directive (deduped per order+status), and a handler
calls the iFood order-action API with retry semantics.

Directive over synchronous call: the callback crosses the network and iFood may
be briefly unavailable — a Directive gives at-least-once delivery with backoff,
per ADR-003.
"""

from __future__ import annotations

import logging

from shopman.orderman.exceptions import DirectiveTransientError
from shopman.orderman.models import Directive

from shopman.shop.directives import IFOOD_STATUS_CALLBACK
from shopman.shop.services import ifood_callbacks, ifood_ingest

logger = logging.getLogger(__name__)


class IFoodStatusCallbackHandler:
    topic = IFOOD_STATUS_CALLBACK

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload
        order_id = payload.get("ifood_order_id") or payload.get("external_ref")
        status = payload.get("status", "")
        if not order_id:
            logger.warning("ifood_status: directive without ifood_order_id: %s", payload)
            return

        try:
            sent = ifood_callbacks.send_for_status(
                order_id, status, cancellation_reason=payload.get("cancellation_reason", "")
            )
        except ifood_callbacks.IFoodCallbackError as exc:
            raise DirectiveTransientError(str(exc)) from exc

        if not sent:
            logger.info("ifood_status: no iFood action for status=%s (order %s)", status, order_id)


# ── Signal receiver ────────────────────────────────────────────────────────────


def on_order_status_changed(sender, order, event_type, actor, **kwargs) -> None:
    """Enqueue an iFood callback when an iFood-channel order changes status."""
    if event_type != "status_changed":
        return
    if getattr(order, "channel_ref", "") != ifood_ingest.IFOOD_CHANNEL_REF:
        return
    if ifood_callbacks.action_for_status(order.status) is None:
        return

    ifood_order_id = order.external_ref or (order.data or {}).get("external_order_code", "")
    if not ifood_order_id:
        logger.warning("ifood_status: order %s has no iFood order id — cannot call back", order.ref)
        return

    dedupe_key = f"{IFOOD_STATUS_CALLBACK}:{order.ref}:{order.status}"
    exists = Directive.objects.filter(
        dedupe_key=dedupe_key,
        status__in=("queued", "running"),
    ).exists()
    if exists:
        return

    Directive.objects.create(
        topic=IFOOD_STATUS_CALLBACK,
        payload={
            "order_ref": order.ref,
            "ifood_order_id": ifood_order_id,
            "status": order.status,
            # cancellation.cancel writes this to order.data before the signal fires.
            "cancellation_reason": (order.data or {}).get("cancellation_reason", ""),
        },
        dedupe_key=dedupe_key,
    )
    logger.debug("ifood_status: enqueued %s callback for order %s", order.status, order.ref)


__all__ = ["IFoodStatusCallbackHandler", "on_order_status_changed"]
