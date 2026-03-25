"""
Mock Payment Backend — Para desenvolvimento e testes.

Persiste via PaymentService (DB) + simula gateway in-memory.
"""

from __future__ import annotations

import json
import logging
from datetime import timedelta
from uuid import uuid4

from django.utils import timezone
from shopman.payments.protocols import (
    CaptureResult,
    GatewayIntent,
    PaymentStatus,
    RefundResult,
)

logger = logging.getLogger(__name__)


class MockPaymentBackend:
    """
    Backend mock para desenvolvimento e testes.

    Simula fluxo completo de pagamento com persistência via PaymentService.
    Todos os pagamentos são aprovados automaticamente.

    Uso:
        backend = MockPaymentBackend()
        intent = backend.create_intent(5000, "BRL", reference="ORD-001")
        result = backend.capture(intent.intent_id)
    """

    def __init__(self, *, auto_authorize: bool = True, fail_rate: float = 0.0):
        self.auto_authorize = auto_authorize
        self.fail_rate = fail_rate

    def create_intent(
        self,
        amount_q: int,
        currency: str,
        *,
        reference: str | None = None,
        metadata: dict | None = None,
    ) -> GatewayIntent:
        """Cria intenção de pagamento mock com persistência via PaymentService."""
        from shopman.payments import PaymentService

        pix_timeout = (metadata or {}).get("pix_timeout_minutes", 30)
        expires_at = timezone.now() + timedelta(minutes=pix_timeout)

        # 1. Persist via PaymentService
        db_intent = PaymentService.create_intent(
            order_ref=reference or "",
            amount_q=amount_q,
            method="pix",
            gateway="mock",
            gateway_data=metadata or {},
            expires_at=expires_at,
        )

        # 2. Simulate gateway — generate mock PIX data
        gateway_id = f"mock_pi_{uuid4().hex[:12]}"
        mock_brcode = (
            f"00020126580014br.gov.bcb.pix0136mock-{gateway_id}"
            f"5204000053039865404{amount_q / 100:.2f}"
            f"5802BR5913NELSON BAKERY6008LONDRINA62070503***6304MOCK"
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
        client_secret_json = json.dumps({
            "qrcode": mock_qr_svg,
            "brcode": mock_brcode,
        })

        # 3. Store gateway_id on the DB intent
        db_intent.gateway_id = gateway_id
        db_intent.gateway_data = {**(metadata or {}), "client_secret": client_secret_json}
        db_intent.save(update_fields=["gateway_id", "gateway_data"])

        # 4. Auto-authorize if configured
        status = "pending"
        if self.auto_authorize:
            PaymentService.authorize(db_intent.ref, gateway_id=gateway_id)
            status = "authorized"

        return GatewayIntent(
            intent_id=db_intent.ref,
            status=status,
            amount_q=amount_q,
            currency=currency,
            client_secret=client_secret_json,
            expires_at=expires_at,
            metadata=metadata,
        )

    def authorize(
        self,
        intent_id: str,
        *,
        payment_method: str | None = None,
    ) -> CaptureResult:
        """Autoriza pagamento mock via PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        if self._should_fail():
            return CaptureResult(
                success=False,
                error_code="card_declined",
                message="Pagamento recusado (simulado)",
            )

        try:
            intent = PaymentService.authorize(
                intent_id,
                gateway_id=f"mock_auth_{intent_id}",
            )
            return CaptureResult(
                success=True,
                transaction_id=f"mock_auth_{intent_id}",
                amount_q=intent.amount_q,
            )
        except PaymentError as e:
            return CaptureResult(
                success=False,
                error_code=e.code,
                message=e.message,
            )

    def capture(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reference: str | None = None,
    ) -> CaptureResult:
        """Captura pagamento mock via PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        if self._should_fail():
            return CaptureResult(
                success=False,
                error_code="capture_failed",
                message="Captura falhou (simulado)",
            )

        try:
            txn = PaymentService.capture(intent_id, amount_q=amount_q)
            return CaptureResult(
                success=True,
                transaction_id=f"mock_txn_{intent_id}",
                amount_q=txn.amount_q,
            )
        except PaymentError as e:
            return CaptureResult(
                success=False,
                error_code=e.code,
                message=e.message,
            )

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Processa reembolso mock via PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        try:
            txn = PaymentService.refund(
                intent_id,
                amount_q=amount_q,
                reason=reason or "",
            )
            return RefundResult(
                success=True,
                refund_id=f"mock_refund_{uuid4().hex[:8]}",
                amount_q=txn.amount_q,
            )
        except PaymentError as e:
            return RefundResult(
                success=False,
                error_code=e.code,
                message=e.message,
            )

    def cancel(self, intent_id: str) -> bool:
        """Cancela intenção mock via PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        try:
            PaymentService.cancel(intent_id)
            return True
        except PaymentError:
            return False

    def get_status(self, intent_id: str) -> PaymentStatus:
        """Consulta status via PaymentService."""
        from shopman.payments import PaymentError, PaymentService

        try:
            intent = PaymentService.get(intent_id)
            captured_q = PaymentService.captured_total(intent_id)
            refunded_q = PaymentService.refunded_total(intent_id)

            return PaymentStatus(
                intent_id=intent_id,
                status=intent.status,
                amount_q=intent.amount_q,
                captured_q=captured_q,
                refunded_q=refunded_q,
                currency=intent.currency,
                metadata=intent.gateway_data,
            )
        except PaymentError:
            return PaymentStatus(
                intent_id=intent_id,
                status="not_found",
                amount_q=0,
                captured_q=0,
                refunded_q=0,
                currency="",
            )

    def _should_fail(self) -> bool:
        """Verifica se deve simular falha."""
        if self.fail_rate <= 0:
            return False
        import random
        return random.random() < self.fail_rate
