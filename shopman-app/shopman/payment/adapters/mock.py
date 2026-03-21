"""
Mock Payment Backend — Para desenvolvimento e testes.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

from django.utils import timezone

from shopman.payment.protocols import (
    CaptureResult,
    PaymentIntent,
    PaymentStatus,
    RefundResult,
)


class MockPaymentBackend:
    """
    Backend mock para desenvolvimento e testes.

    Simula fluxo completo de pagamento sem integração externa.
    Todos os pagamentos são aprovados automaticamente.

    Uso:
        backend = MockPaymentBackend()
        intent = backend.create_intent(5000, "BRL")
        result = backend.capture(intent.intent_id)
    """

    def __init__(self, *, auto_authorize: bool = True, fail_rate: float = 0.0):
        """
        Args:
            auto_authorize: Se True, create_intent já retorna status "authorized"
            fail_rate: Taxa de falha simulada (0.0 a 1.0)
        """
        self.auto_authorize = auto_authorize
        self.fail_rate = fail_rate
        self._intents: dict[str, dict] = {}

    def create_intent(
        self,
        amount_q: int,
        currency: str,
        *,
        reference: str | None = None,
        metadata: dict | None = None,
    ) -> PaymentIntent:
        """Cria intenção de pagamento mock."""
        intent_id = f"mock_pi_{uuid4().hex[:12]}"

        status = "authorized" if self.auto_authorize else "pending"

        self._intents[intent_id] = {
            "intent_id": intent_id,
            "status": status,
            "amount_q": amount_q,
            "currency": currency,
            "captured_q": 0,
            "refunded_q": 0,
            "reference": reference,
            "metadata": metadata or {},
            "created_at": timezone.now(),
        }

        # Generate mock PIX data in client_secret (JSON) for PixGenerateHandler
        import json

        pix_timeout = (metadata or {}).get("pix_timeout_minutes", 30)
        mock_brcode = (
            f"00020126580014br.gov.bcb.pix0136mock-{intent_id}"
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

        return PaymentIntent(
            intent_id=intent_id,
            status=status,
            amount_q=amount_q,
            currency=currency,
            client_secret=client_secret_json,
            expires_at=timezone.now() + timedelta(minutes=pix_timeout),
            metadata=metadata,
        )

    def authorize(
        self,
        intent_id: str,
        *,
        payment_method: str | None = None,
    ) -> CaptureResult:
        """Autoriza pagamento mock."""
        intent = self._intents.get(intent_id)
        if not intent:
            return CaptureResult(
                success=False,
                error_code="intent_not_found",
                message=f"Intent {intent_id} não encontrado",
            )

        if self._should_fail():
            return CaptureResult(
                success=False,
                error_code="card_declined",
                message="Pagamento recusado (simulado)",
            )

        intent["status"] = "authorized"

        return CaptureResult(
            success=True,
            transaction_id=f"mock_auth_{intent_id}",
            amount_q=intent["amount_q"],
        )

    def capture(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reference: str | None = None,
    ) -> CaptureResult:
        """Captura pagamento mock."""
        intent = self._intents.get(intent_id)
        if not intent:
            return CaptureResult(
                success=False,
                error_code="intent_not_found",
                message=f"Intent {intent_id} não encontrado",
            )

        if intent["status"] not in ("pending", "authorized"):
            return CaptureResult(
                success=False,
                error_code="invalid_status",
                message=f"Intent em status inválido: {intent['status']}",
            )

        if self._should_fail():
            return CaptureResult(
                success=False,
                error_code="capture_failed",
                message="Captura falhou (simulado)",
            )

        capture_amount = amount_q or intent["amount_q"]
        intent["status"] = "captured"
        intent["captured_q"] = capture_amount
        if reference:
            intent["reference"] = reference

        return CaptureResult(
            success=True,
            transaction_id=f"mock_txn_{intent_id}",
            amount_q=capture_amount,
        )

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """Processa reembolso mock."""
        intent = self._intents.get(intent_id)
        if not intent:
            return RefundResult(
                success=False,
                error_code="intent_not_found",
                message=f"Intent {intent_id} não encontrado",
            )

        if intent["status"] != "captured":
            return RefundResult(
                success=False,
                error_code="not_captured",
                message="Só é possível reembolsar pagamentos capturados",
            )

        refund_amount = amount_q or intent["captured_q"]
        max_refundable = intent["captured_q"] - intent["refunded_q"]

        if refund_amount > max_refundable:
            return RefundResult(
                success=False,
                error_code="exceeds_captured",
                message=f"Valor excede máximo reembolsável: {max_refundable}",
            )

        intent["refunded_q"] += refund_amount
        if intent["refunded_q"] >= intent["captured_q"]:
            intent["status"] = "refunded"

        return RefundResult(
            success=True,
            refund_id=f"mock_refund_{uuid4().hex[:8]}",
            amount_q=refund_amount,
        )

    def cancel(self, intent_id: str) -> bool:
        """Cancela intenção mock."""
        intent = self._intents.get(intent_id)
        if not intent:
            return False

        if intent["status"] in ("captured", "refunded"):
            return False

        intent["status"] = "cancelled"
        return True

    def get_status(self, intent_id: str) -> PaymentStatus:
        """Consulta status mock."""
        intent = self._intents.get(intent_id)
        if not intent:
            return PaymentStatus(
                intent_id=intent_id,
                status="not_found",
                amount_q=0,
                captured_q=0,
                refunded_q=0,
                currency="",
            )

        return PaymentStatus(
            intent_id=intent_id,
            status=intent["status"],
            amount_q=intent["amount_q"],
            captured_q=intent["captured_q"],
            refunded_q=intent["refunded_q"],
            currency=intent["currency"],
            metadata=intent["metadata"],
        )

    def _should_fail(self) -> bool:
        """Verifica se deve simular falha."""
        if self.fail_rate <= 0:
            return False
        import random
        return random.random() < self.fail_rate
