"""
Stripe payment adapter — card payments via Stripe with 3D Secure.

Persists via PaymentService (DB) + communicates with Stripe API.
Requires: pip install stripe
"""

from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_config() -> dict:
    """Read Stripe configuration from settings."""
    return getattr(settings, "SHOPMAN_STRIPE", {})


def _get_stripe():
    """Lazy import of stripe SDK."""
    try:
        import stripe
    except ImportError as err:
        raise ImportError(
            "stripe package is required. Install with: pip install stripe"
        ) from err
    config = _get_config()
    stripe.api_key = config.get("secret_key")
    return stripe


def create_intent(order_ref: str, amount_q: int, method: str = "card", **config) -> dict:
    """
    Create a Stripe PaymentIntent + persist via PaymentService.

    The client_secret is used by the frontend (Stripe Elements) to confirm payment.

    Returns:
        {"intent_ref": str, "status": str, "client_secret": str,
         "gateway_id": str}
    """
    from shopman.payments import PaymentService

    stripe_config = _get_config()
    capture_method = stripe_config.get("capture_method", "manual")
    currency = config.get("currency", "BRL").lower()
    metadata = config.get("metadata", {})

    db_intent = PaymentService.create_intent(
        order_ref=order_ref,
        amount_q=amount_q,
        method="card",
        gateway="stripe",
        gateway_data=metadata,
    )

    stripe = _get_stripe()
    stripe_intent = stripe.PaymentIntent.create(
        amount=amount_q,
        currency=currency,
        capture_method=capture_method,
        metadata={
            "shopman_ref": db_intent.ref,
            "order_ref": order_ref,
            **metadata,
        },
    )

    db_intent.gateway_id = stripe_intent.id
    db_intent.gateway_data = {
        **metadata,
        "stripe_status": stripe_intent.status,
    }
    db_intent.save(update_fields=["gateway_id", "gateway_data"])

    status = "pending"
    if stripe_intent.status == "requires_action":
        status = "requires_action"

    return {
        "intent_ref": db_intent.ref,
        "status": status,
        "client_secret": stripe_intent.client_secret,
        "gateway_id": stripe_intent.id,
    }


def capture(intent_ref: str, amount_q: int | None = None, **config) -> dict:
    """
    Capture a Stripe PaymentIntent.

    For capture_method="automatic", payment is already captured.
    For capture_method="manual", calls stripe.PaymentIntent.capture().

    Returns:
        {"success": bool, "transaction_id": str | None, "amount_q": int | None,
         "error_code": str | None, "message": str | None}
    """
    from shopman.payments import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError as e:
        return {
            "success": False,
            "transaction_id": None,
            "amount_q": None,
            "error_code": e.code,
            "message": e.message,
        }

    stripe = _get_stripe()

    try:
        capture_params = {}
        if amount_q is not None:
            capture_params["amount_to_capture"] = amount_q

        stripe_intent = stripe.PaymentIntent.capture(
            intent.gateway_id,
            **capture_params,
        )

        txn = PaymentService.capture(
            intent_ref,
            amount_q=amount_q,
            gateway_id=stripe_intent.id,
        )

        return {
            "success": True,
            "transaction_id": stripe_intent.latest_charge,
            "amount_q": txn.amount_q,
            "error_code": None,
            "message": None,
        }
    except Exception as e:
        logger.exception("Stripe capture error for %s", intent_ref)
        return {
            "success": False,
            "transaction_id": None,
            "amount_q": None,
            "error_code": "stripe_error",
            "message": str(e),
        }


def refund(intent_ref: str, amount_q: int | None = None, **config) -> dict:
    """
    Process refund via Stripe + PaymentService.

    Returns:
        {"success": bool, "refund_id": str | None, "amount_q": int | None,
         "error_code": str | None, "message": str | None}
    """
    from shopman.payments import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError as e:
        return {
            "success": False,
            "refund_id": None,
            "amount_q": None,
            "error_code": e.code,
            "message": e.message,
        }

    stripe = _get_stripe()

    try:
        refund_params = {"payment_intent": intent.gateway_id}
        if amount_q is not None:
            refund_params["amount"] = amount_q
        reason = config.get("reason")
        if reason:
            refund_params["reason"] = "requested_by_customer"

        stripe_refund = stripe.Refund.create(**refund_params)

        refund_amount = stripe_refund.amount
        try:
            PaymentService.refund(
                intent_ref,
                amount_q=refund_amount,
                reason=reason or "",
                gateway_id=stripe_refund.id,
            )
        except PaymentError:
            pass

        return {
            "success": True,
            "refund_id": stripe_refund.id,
            "amount_q": refund_amount,
            "error_code": None,
            "message": None,
        }
    except Exception as e:
        logger.exception("Stripe refund error for %s", intent_ref)
        return {
            "success": False,
            "refund_id": None,
            "amount_q": None,
            "error_code": "stripe_error",
            "message": str(e),
        }


def cancel(intent_ref: str, **config) -> dict:
    """
    Cancel a Stripe PaymentIntent + PaymentService.

    Returns:
        {"success": bool, "error_code": str | None, "message": str | None}
    """
    from shopman.payments import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
    except PaymentError:
        return {"success": False, "error_code": "intent_not_found", "message": "Intent não encontrado"}

    stripe = _get_stripe()

    try:
        stripe.PaymentIntent.cancel(intent.gateway_id)

        try:
            PaymentService.cancel(intent_ref)
        except PaymentError:
            pass

        return {"success": True, "error_code": None, "message": None}
    except Exception as e:
        logger.warning("Stripe cancel failed for %s: %s", intent_ref, e, exc_info=True)
        return {"success": False, "error_code": "stripe_error", "message": str(e)}


def get_status(intent_ref: str, **config) -> dict:
    """
    Get payment status from PaymentService (source of truth).

    Returns:
        {"intent_ref": str, "status": str, "amount_q": int,
         "captured_q": int, "refunded_q": int, "currency": str}
    """
    from shopman.payments import PaymentError, PaymentService

    try:
        intent = PaymentService.get(intent_ref)
        captured_q = PaymentService.captured_total(intent_ref)
        refunded_q = PaymentService.refunded_total(intent_ref)

        return {
            "intent_ref": intent_ref,
            "status": intent.status,
            "amount_q": intent.amount_q,
            "captured_q": captured_q,
            "refunded_q": refunded_q,
            "currency": intent.currency,
        }
    except PaymentError:
        return {
            "intent_ref": intent_ref,
            "status": "not_found",
            "amount_q": 0,
            "captured_q": 0,
            "refunded_q": 0,
            "currency": "",
        }


def handle_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Process a Stripe webhook event.

    Called by the webhook view. Verifies signature and processes event.

    Returns:
        {"event_type": str, "intent_ref": str | None}
    """
    from shopman.payments import PaymentError, PaymentService

    stripe = _get_stripe()
    stripe_config = _get_config()
    event = stripe.Webhook.construct_event(
        payload, sig_header, stripe_config.get("webhook_secret"),
    )

    intent_ref = None

    if event.type == "payment_intent.succeeded":
        stripe_intent = event.data.object
        shopman_ref = stripe_intent.metadata.get("shopman_ref")
        if shopman_ref:
            intent_ref = shopman_ref
            try:
                PaymentService.authorize(shopman_ref, gateway_id=stripe_intent.id)
            except PaymentError:
                pass
            try:
                PaymentService.capture(shopman_ref, gateway_id=stripe_intent.id)
            except PaymentError:
                pass

    elif event.type == "payment_intent.payment_failed":
        stripe_intent = event.data.object
        shopman_ref = stripe_intent.metadata.get("shopman_ref")
        if shopman_ref:
            intent_ref = shopman_ref
            last_error = stripe_intent.last_payment_error
            try:
                PaymentService.fail(
                    shopman_ref,
                    error_code=last_error.code if last_error else "unknown",
                    message=last_error.message if last_error else "",
                )
            except PaymentError:
                pass

    elif event.type == "charge.refunded":
        charge = event.data.object
        stripe_intent_id = charge.payment_intent
        if stripe_intent_id:
            db_intent = PaymentService.get_by_gateway_id(stripe_intent_id)
            if db_intent:
                intent_ref = db_intent.ref
                try:
                    PaymentService.refund(
                        db_intent.ref,
                        amount_q=charge.amount_refunded,
                        gateway_id=charge.id,
                    )
                except PaymentError:
                    pass

    return {"event_type": event.type, "intent_ref": intent_ref}
