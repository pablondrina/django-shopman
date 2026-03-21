"""
Shopman Payment — Processamento de pagamentos.

Uso:
    from shopman.payment.protocols import PaymentBackend
    from shopman.payment.handlers import PaymentCaptureHandler

Para desenvolvimento/testes:
    from shopman.payment.adapters.mock import MockPaymentBackend

Para Stripe:
    from shopman.payment.adapters.stripe import StripeBackend

Para Pix (Efi/antigo Gerencianet):
    from shopman.payment.adapters.efi import EfiPixBackend
"""

default_app_config = "shopman.payment.apps.PaymentConfig"

from .protocols import (
    PaymentBackend,
    PaymentIntent,
    CaptureResult,
    RefundResult,
    PaymentStatus,
)

__all__ = [
    "PaymentBackend",
    "PaymentIntent",
    "CaptureResult",
    "RefundResult",
    "PaymentStatus",
]
