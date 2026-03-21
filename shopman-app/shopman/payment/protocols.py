"""
Shopman Payment Protocols — Re-exports from core.

For backwards compatibility. Import from shopman.ordering.protocols instead.
"""

from shopman.ordering.protocols import (
    CaptureResult,
    PaymentBackend,
    PaymentIntent,
    PaymentStatus,
    RefundResult,
)

__all__ = [
    "PaymentIntent",
    "CaptureResult",
    "RefundResult",
    "PaymentStatus",
    "PaymentBackend",
]
