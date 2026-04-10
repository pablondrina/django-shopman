"""
Channel protocols — contratos de backend consolidados.

Protocols que vivem no omniman core são re-exportados.
Protocols que viviam nos mini-apps são definidos inline aqui.
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Fiscal, Accounting ── (vivem no omniman core, re-export)
from shopman.omniman.protocols import (  # noqa: F401
    AccountingBackend,
    FiscalBackend,
)

# ── Payment ── (vivem no payments core, re-export)
from shopman.payman.protocols import (  # noqa: F401
    CaptureResult,
    GatewayIntent,
    PaymentBackend,
    PaymentStatus,
    RefundResult,
)

# Note: Stock no longer has a class-based protocol — the canonical entrypoint
# is the module `shopman.adapters.stock` (function-style adapter resolved via
# `get_adapter("stock")`). See ADR-001 for the protocol/adapter pattern.


# ── Notification (inline — era shopman.notifications.protocols) ──


@dataclass(frozen=True)
class NotificationResult:
    """Resultado do envio."""

    success: bool
    message_id: str | None = None
    error: str | None = None


# ── Pricing (inline — era shopman.pricing.protocols) ──


__all__ = [
    # Payment
    "PaymentBackend",
    "GatewayIntent",
    "CaptureResult",
    "RefundResult",
    "PaymentStatus",
    # Fiscal
    "FiscalBackend",
    # Accounting
    "AccountingBackend",
    # Notification
    "NotificationResult",
]
