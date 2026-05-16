"""
Shopman Payman — Payment Lifecycle Management.

Usage:
    from shopman.payman import PaymentService, PaymentError

    intent = PaymentService.create_intent("ORD-001", 1500, "pix")
    PaymentService.authorize(intent.ref, gateway_id="efi_txid_123")
    tx = PaymentService.capture(intent.ref)
    PaymentService.refund(intent.ref, amount_q=500, reason="item danificado")

5 verbs: create_intent, authorize, capture, refund, cancel.
2 queries: get, get_by_order.
1 helper: get_active_intent.

Philosophy: SIREL (Simples, Robusto, Elegante)
"""

from shopman.payman.exceptions import PaymentError


def __getattr__(name):
    """Lazy import to avoid AppRegistryNotReady errors."""
    if name == "PaymentService":
        from shopman.payman.service import PaymentService

        return PaymentService
    if name == "PaymentIntent":
        from shopman.payman.models.intent import PaymentIntent

        return PaymentIntent
    if name == "PaymentTransaction":
        from shopman.payman.models.transaction import PaymentTransaction

        return PaymentTransaction
    if name == "PaymentReconciliationResult":
        from shopman.payman.service import PaymentReconciliationResult

        return PaymentReconciliationResult
    # Protocol DTOs (no DB dependency, safe to import eagerly)
    _protocol_names = {"GatewayIntent", "CaptureResult", "RefundResult", "PaymentStatus", "PaymentBackend"}
    if name in _protocol_names:
        import shopman.payman.protocols as _p

        return getattr(_p, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PaymentService",
    "PaymentError",
    "PaymentIntent",
    "PaymentTransaction",
    "PaymentReconciliationResult",
    # Protocols (gateway DTOs)
    "GatewayIntent",
    "CaptureResult",
    "RefundResult",
    "PaymentStatus",
    "PaymentBackend",
]

__version__ = "0.2.0"
