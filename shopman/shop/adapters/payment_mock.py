"""
Mock payment adapter for development and testing.

Persists via PaymentService (DB) + simulates gateway in-memory.
All payments succeed by default.

Returns canonical DTOs from shopman.shop.adapters.payment_types.
"""

from __future__ import annotations

import base64
import io
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

    For ``method="pix"`` this creates the QR/payment intent only. Manual dev
    flows must confirm payment explicitly through the storefront dev action.
    Tests that need to exercise the asynchronous webhook parity path can opt
    in with ``mock_pix_auto_confirm=True``.
    """
    from shopman.orderman.models import Directive
    from shopman.payman import PaymentService

    metadata = metadata or {}
    idempotency_key = config.get("idempotency_key") or metadata.get("idempotency_key", "")
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
        idempotency_key=idempotency_key,
    )
    if db_intent.gateway_id and db_intent.gateway_data.get("client_secret"):
        return _intent_from_db(db_intent, currency=currency)

    gateway_id = f"mock_pi_{uuid4().hex[:12]}"
    mock_brcode = (
        f"00020126580014br.gov.bcb.pix0136mock-{gateway_id}"
        f"5204000053039865404{amount_q / 100:.2f}"
        f"5802BR5913MOCK6008SHOPMAN62070503***6304MOCK"
    )
    mock_qr_image = _qr_png_data_url(mock_brcode)
    client_secret = json.dumps({"qrcode": mock_brcode, "brcode": mock_brcode, "imagemQrcode": mock_qr_image})

    db_intent.gateway_id = gateway_id
    db_intent.gateway_data = {**metadata, "client_secret": client_secret}
    db_intent.save(update_fields=["gateway_id", "gateway_data"])

    status = db_intent.status
    if auto_authorize and db_intent.status == "pending":
        PaymentService.authorize(db_intent.ref, gateway_id=gateway_id)
        status = "authorized"

    if method == "pix" and config.get("mock_pix_auto_confirm") is True:
        delay_seconds = int(config.get("mock_pix_confirm_delay_seconds", 10))
        available_at = timezone.now() + timedelta(seconds=delay_seconds)
        Directive.objects.create(
            topic="mock_pix.confirm",
            payload={
                "order_ref": order_ref,
                "txid": gateway_id,
                "e2e_id": f"E2E{uuid4().hex[:24].upper()}",
                "valor": f"{amount_q / 100:.2f}",
                "mock_pix_auto_confirm": True,
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
        metadata={"qrcode": mock_brcode, "brcode": mock_brcode, "imagemQrcode": mock_qr_image},
    )


def _intent_from_db(intent, *, currency: str = "BRL") -> PaymentIntent:
    client_secret = (intent.gateway_data or {}).get("client_secret")
    metadata = dict(intent.gateway_data or {})
    if client_secret:
        try:
            parsed = json.loads(client_secret)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        if isinstance(parsed, dict):
            metadata.update(parsed)
    return PaymentIntent(
        intent_ref=intent.ref,
        status=intent.status,
        amount_q=intent.amount_q,
        currency=currency or intent.currency,
        client_secret=client_secret,
        expires_at=intent.expires_at,
        gateway_id=intent.gateway_id,
        metadata=metadata,
    )


def _qr_png_data_url(value: str) -> str:
    """Return a real scannable QR image as a PNG data URL for local PIX testing."""
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M

    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=6,
        border=4,
    )
    qr.add_data(value)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


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
