"""
PIX confirmation — canonical handler shared by every ingress path.

The same body of code runs for:

1. **Real EFI webhook.** ``EfiPixWebhookView`` authenticates the request
   (mTLS + shared token) and delegates to :func:`confirm_pix`.
2. **Mock PIX backend.** ``adapters.payment_mock`` schedules a
   ``mock_pix.confirm`` directive at ``create_intent`` time; the
   ``MockPixConfirmHandler`` fires after the configured delay and calls
   :func:`confirm_pix`.
3. **Tests.** Integration tests call :func:`confirm_pix` directly to
   exercise the downstream flow without going through HTTP.

There is no environment branch here — dev and prod run the same code. The
only thing that differs is *who calls it*: EFI's servers in production, the
mock backend's scheduled directive in development.
"""

from __future__ import annotations

import logging

from shopman.orderman.models import Order

logger = logging.getLogger(__name__)


def confirm_pix(*, txid: str, e2e_id: str = "", valor: str = "") -> None:
    """Record a PIX payment as captured and dispatch ``on_paid``.

    Parameters
    ----------
    txid:
        The PIX transaction id. Used to locate the ``PaymentIntent`` via
        ``PaymentService.get_by_gateway_id``. Falls back to a scan of
        ``Order.data.payment.intent_ref`` for legacy orders that did not
        persist a gateway id at creation time.
    e2e_id:
        End-to-end transaction id from the PIX network. Used for
        idempotency — a second webhook for the same ``e2e_id`` is a noop.
    valor:
        Paid amount as a decimal string (``"12.50"``). Converted to
        centavos for ``PaymentService.capture``.
    """
    from shopman.payman import PaymentError, PaymentService

    db_intent = PaymentService.get_by_gateway_id(txid)

    if db_intent is None:
        order = (
            Order.objects
            .filter(data__payment__intent_ref__icontains=txid)
            .first()
        )
        if order is None:
            logger.warning(
                "pix_confirmation: no payment intent or order for txid=%s", txid,
            )
            return
        _apply_order_payment(order, e2e_id=e2e_id, valor=valor)
        return

    amount_q = int(round(float(valor) * 100)) if valor else db_intent.amount_q

    try:
        if db_intent.status == "pending":
            PaymentService.authorize(
                db_intent.ref,
                gateway_id=txid,
                gateway_data={"e2e_id": e2e_id},
            )
        if db_intent.status in ("pending", "authorized"):
            PaymentService.capture(
                db_intent.ref,
                amount_q=amount_q,
                gateway_id=txid,
            )
    except PaymentError as e:
        if e.code != "invalid_transition":
            raise

    order = (
        Order.objects
        .filter(data__payment__intent_ref=db_intent.ref)
        .first()
    )
    if order is None:
        try:
            order = Order.objects.get(ref=db_intent.order_ref)
        except Order.DoesNotExist:
            logger.warning(
                "pix_confirmation: intent %s authorized but order %s not found",
                db_intent.ref, db_intent.order_ref,
            )
            return

    _apply_order_payment(order, e2e_id=e2e_id, valor=valor)


def _apply_order_payment(order: Order, *, e2e_id: str, valor: str) -> None:
    """Record PIX transaction audit data on the order and dispatch ``on_paid``.

    Idempotent on ``e2e_id``: a second call with the same end-to-end id is
    a noop (returns without dispatching).
    """
    from shopman.shop.lifecycle import dispatch

    payment_data = order.data.get("payment", {}) if order.data else {}

    if e2e_id and payment_data.get("e2e_id") == e2e_id:
        return

    if e2e_id:
        payment_data["e2e_id"] = e2e_id
    if valor:
        payment_data["paid_amount_q"] = int(round(float(valor) * 100))

    if order.data is None:
        order.data = {}
    order.data["payment"] = payment_data
    order.save(update_fields=["data", "updated_at"])

    dispatch(order, "on_paid")


__all__ = ["confirm_pix"]
