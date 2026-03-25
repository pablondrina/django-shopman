"""
Payment Protocols — Interfaces para backends de gateway.

Os DTOs e protocols definem o contrato entre os handlers do App
e os backends de gateway (Mock, Efi, Stripe, etc.).

O PaymentService (service.py) gerencia o lifecycle no DB.
Os backends implementam a comunicação com o gateway externo.

Uso:
    from shopman.payments.protocols import PaymentBackend, GatewayIntent, CaptureResult
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class GatewayIntent:
    """Intenção de pagamento retornada pelo gateway."""

    intent_id: str
    status: str  # "pending", "authorized", "requires_action", "captured", "failed"
    amount_q: int
    currency: str
    client_secret: str | None = None  # Para frontend (Stripe Elements, QR code, etc)
    expires_at: datetime | None = None
    metadata: dict | None = None


@dataclass(frozen=True)
class CaptureResult:
    """Resultado de captura/autorização."""

    success: bool
    transaction_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class RefundResult:
    """Resultado de reembolso."""

    success: bool
    refund_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class PaymentStatus:
    """Status atual do pagamento no gateway."""

    intent_id: str
    status: str  # "pending", "authorized", "captured", "refunded", "failed", "cancelled"
    amount_q: int
    captured_q: int
    refunded_q: int
    currency: str
    metadata: dict | None = None


@runtime_checkable
class PaymentBackend(Protocol):
    """
    Protocol para backends de pagamento (gateway).

    Implementações:
    - channels.backends.payment_mock.MockPaymentBackend
    - channels.backends.payment_efi.EfiPixBackend
    - channels.backends.payment_stripe.StripeBackend
    """

    def create_intent(
        self,
        amount_q: int,
        currency: str,
        *,
        reference: str | None = None,
        metadata: dict | None = None,
    ) -> GatewayIntent: ...

    def authorize(
        self,
        intent_id: str,
        *,
        payment_method: str | None = None,
    ) -> CaptureResult: ...

    def capture(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reference: str | None = None,
    ) -> CaptureResult: ...

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult: ...

    def cancel(self, intent_id: str) -> bool: ...

    def get_status(self, intent_id: str) -> PaymentStatus: ...
