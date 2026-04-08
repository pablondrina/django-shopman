"""
Payment orchestration service.

Core: PaymentService (create_intent, authorize, capture, refund, cancel)
Adapter: get_adapter("payment", method=...) → payment_efi / payment_stripe / payment_mock

The contract between this service and the adapters is defined in
shopman.adapters.payment_types: adapters return PaymentIntent / PaymentResult
dataclasses, not dicts. This service consumes them by attribute access.
"""

from __future__ import annotations

import json
import logging

from shopman.adapters import get_adapter
from shopman.adapters.payment_types import PaymentIntent

logger = logging.getLogger(__name__)


def initiate(order) -> None:
    """
    Create a payment intent for the order.

    Resolves the adapter by payment method (from order.data["payment"]["method"]),
    calls adapter.create_intent(), then saves intent_ref and client_secret
    in order.data["payment"].

    SYNC — needs the intent/QR data to show to the client.
    """
    payment_data = order.data.get("payment", {})
    method = payment_data.get("method")

    if not method or method in ("counter", "external", "dinheiro"):
        return

    # Idempotent: skip if intent already exists
    if payment_data.get("intent_ref"):
        return

    adapter = get_adapter("payment", method=method)
    if not adapter:
        logger.warning("payment.initiate: no adapter for method=%s", method)
        return

    amount_q = order.total_q
    try:
        intent = adapter.create_intent(
            order_ref=order.ref,
            amount_q=amount_q,
            currency="BRL",
            method=method,
            metadata={"method": method},
        )
    except Exception as exc:
        logger.error(
            "payment.initiate: create_intent failed for order %s method=%s: %s",
            order.ref,
            method,
            exc,
        )
        order.data["payment"] = {
            "method": method,
            "status": "pending_retry",
            "amount_q": amount_q,
            "error": str(exc)[:200],
        }
        order.save(update_fields=["data", "updated_at"])
        return

    # Build payment data to save
    result = {
        "intent_ref": intent.intent_ref,
        "status": intent.status,
        "amount_q": amount_q,
        "method": method,
    }

    # Extract QR/client_secret data
    if method == "pix":
        qr_data = _extract_qr_data(intent)
        result["qr_code"] = qr_data.get("qrcode") or qr_data.get("qr_code")
        result["copy_paste"] = qr_data.get("brcode") or qr_data.get("copy_paste")
        if intent.expires_at:
            result["expires_at"] = intent.expires_at.isoformat()
    elif method == "card":
        result["client_secret"] = intent.client_secret

    order.data["payment"] = result
    order.save(update_fields=["data", "updated_at"])

    logger.info(
        "payment.initiate: %s intent %s for order %s",
        method, intent.intent_ref, order.ref,
    )


def capture(order) -> None:
    """
    Capture a previously authorized payment.

    Reads intent_ref from order.data["payment"] and calls adapter.capture().
    Persists result via Core PaymentService.

    SYNC — capture must succeed.
    """
    payment_data = (order.data or {}).get("payment", {})
    intent_ref = payment_data.get("intent_ref")

    if not intent_ref:
        return

    # Already captured?
    if payment_data.get("status") in ("captured", "paid"):
        return

    method = payment_data.get("method", "pix")
    adapter = get_adapter("payment", method=method)
    if not adapter:
        return

    result = adapter.capture(intent_ref)
    if result.success:
        payment_data["status"] = "captured"
        payment_data["transaction_id"] = result.transaction_id
        order.data["payment"] = payment_data
        order.save(update_fields=["data", "updated_at"])

        logger.info("payment.capture: captured %s for order %s", intent_ref, order.ref)


def refund(order) -> None:
    """
    Refund payment for the order.

    Smart no-op: if order has no payment intent, does nothing.
    Otherwise calls adapter.refund() and persists via Core PaymentService.

    SYNC — direct refund.
    """
    payment_data = (order.data or {}).get("payment", {})
    intent_ref = payment_data.get("intent_ref")

    if not intent_ref:
        # Smart no-op: no payment to refund (counter, external, etc.)
        return

    if payment_data.get("status") == "refunded":
        return

    method = payment_data.get("method", "pix")
    adapter = get_adapter("payment", method=method)
    if not adapter:
        return

    try:
        result = adapter.refund(intent_ref, reason="order_cancelled")
        if result.success:
            payment_data["status"] = "refunded"
            order.data["payment"] = payment_data
            order.save(update_fields=["data", "updated_at"])

            logger.info("payment.refund: refunded %s for order %s", intent_ref, order.ref)
    except Exception as exc:
        logger.warning("payment.refund: failed for order %s: %s", order.ref, exc)


# ── helpers ──


def _extract_qr_data(intent: PaymentIntent) -> dict:
    """Extract QR code data from intent metadata or client_secret."""
    if intent.metadata:
        return intent.metadata

    if intent.client_secret:
        try:
            return json.loads(intent.client_secret)
        except (json.JSONDecodeError, TypeError):
            pass

    return {}
