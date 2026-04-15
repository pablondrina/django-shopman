"""
Mock payment adapter for development and testing.

Persists via PaymentService (DB) + simulates gateway in-memory.
All payments succeed by default.

Returns canonical DTOs from shopman.shop.adapters.payment_types.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from uuid import uuid4

from django.utils import timezone

from shopman.shop.adapters.payment_types import PaymentIntent, PaymentResult

logger = logging.getLogger(__name__)


def create_intent(
    *,
    order_ref: str,
    amount_q: int,
    currency: str = "BRL",
    method: str = "pix",
    metadata: dict | None = None,
    **config,
) -> PaymentIntent:
    """Create a mock payment intent with persistence via PaymentService.

    For ``method="pix"`` this also schedules a ``mock_pix.confirm`` directive
    with ``available_at = now + mock_pix_confirm_delay_seconds`` (default 10).
    When it fires, ``MockPixConfirmHandler`` invokes the same ``confirm_pix``
    service that the real EFI webhook uses, so the downstream flow is
    identical in dev and prod.
    """
    from shopman.orderman.models import Directive
    from shopman.payman import PaymentService

    metadata = metadata or {}
    pix_timeout = config.get("pix_timeout_minutes", 30)
    expires_at = timezone.now() + timedelta(minutes=pix_timeout)
    # Mock backend is "authorized" at the payman level immediately; the PIX
    # capture/on_paid path happens via the scheduled directive below.
    auto_authorize = config.get("auto_authorize", True)

    db_intent = PaymentService.create_intent(
        order_ref=order_ref,
        amount_q=amount_q,
        method=method,
        gateway="mock",
        gateway_data=metadata,
        expires_at=expires_at,
    )

    gateway_id = f"mock_pi_{uuid4().hex[:12]}"
    mock_brcode = (
        f"00020126580014br.gov.bcb.pix0136mock-{gateway_id}"
        f"5204000053039865404{amount_q / 100:.2f}"
        f"5802BR5913MOCK6008SHOPMAN62070503***6304MOCK"
    )
    mock_qr_svg = (
        "data:image/svg+xml;base64,"
        "PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRo"
        "PSIyMDAiIGhlaWdodD0iMjAwIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9"
        "IjIwMCIgZmlsbD0iI2YwZjBmMCIvPjx0ZXh0IHg9IjUwJSIgeT0iNDAlIiBm"
        "b250LXNpemU9IjE0IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjMzMz"
        "Ij5RUiBDb2RlIFBJWDwvdGV4dD48dGV4dCB4PSI1MCUiIHk9IjU1JSIgZm9u"
        "dC1zaXplPSIxMiIgdGV4dC1hbmNob3I9Im1pZGRsZSIgZmlsbD0iIzY2NiI+"
        "KE1vY2spPC90ZXh0Pjwvc3ZnPg=="
    )
    client_secret = json.dumps({"qrcode": mock_qr_svg, "brcode": mock_brcode})

    db_intent.gateway_id = gateway_id
    db_intent.gateway_data = {"client_secret": client_secret}
    db_intent.save(update_fields=["gateway_id", "gateway_data"])

    status = "pending"
    if auto_authorize:
        PaymentService.authorize(db_intent.ref, gateway_id=gateway_id)
        status = "authorized"

    if method == "pix":
        delay_seconds = int(config.get("mock_pix_confirm_delay_seconds", 10))
        available_at = timezone.now() + timedelta(seconds=delay_seconds)
        Directive.objects.create(
            topic="mock_pix.confirm",
            payload={
                "order_ref": order_ref,
                "txid": gateway_id,
                "e2e_id": f"E2E{uuid4().hex[:24].upper()}",
                "valor": f"{amount_q / 100:.2f}",
            },
            available_at=available_at,
        )
        logger.info(
            "payment_mock: scheduled mock_pix.confirm for order=%s txid=%s in %ss",
            order_ref, gateway_id, delay_seconds,
        )

    return PaymentIntent(
        intent_ref=db_intent.ref,
        status=status,
        amount_q=amount_q,
        currency=currency,
        client_secret=client_secret,
        expires_at=expires_at,
        gateway_id=gateway_id,
        metadata={"qrcode": mock_qr_svg, "brcode": mock_brcode},
    )


def capture(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    **config,
) -> PaymentResult:
    """Capture mock payment via PaymentService."""
    from shopman.payman import PaymentError, PaymentService

    try:
        txn = PaymentService.capture(intent_ref, amount_q=amount_q)
        return PaymentResult(
            success=True,
            transaction_id=f"mock_txn_{intent_ref}",
            amount_q=txn.amount_q,
        )
    except PaymentError as e:
        return PaymentResult(
            success=False,
            error_code=e.code,
            message=e.message,
        )


def refund(
    intent_ref: str,
    *,
    amount_q: int | None = None,
    reason: str = "",
    **config,
) -> PaymentResult:
    """Process mock refund via PaymentService."""
    from shopman.payman import PaymentError, PaymentService

    try:
        txn = PaymentService.refund(
            intent_ref,
            amount_q=amount_q,
            reason=reason,
        )
        return PaymentResult(
            success=True,
            transaction_id=f"mock_refund_{uuid4().hex[:8]}",
            amount_q=txn.amount_q,
        )
    except PaymentError as e:
        return PaymentResult(
            success=False,
            error_code=e.code,
            message=e.message,
        )


def cancel(intent_ref: str, **config) -> PaymentResult:
    """Cancel mock payment intent via PaymentService."""
    from shopman.payman import PaymentError, PaymentService

    try:
        PaymentService.cancel(intent_ref)
        return PaymentResult(success=True)
    except PaymentError as e:
        return PaymentResult(
            success=False,
            error_code=e.code,
            message=e.message,
        )


def get_status(intent_ref: str, **config) -> dict:
    """Get payment status from PaymentService.

    Returns a plain dict because get_status is a read-only convenience that
    doesn't participate in the orchestrator contract.
    """
    from shopman.payman import PaymentError, PaymentService

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
