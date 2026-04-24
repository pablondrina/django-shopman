"""
Mock PIX confirmation handler — dev parity for the EFI webhook path.

In production, EFI calls :class:`EfiPixWebhookView` which delegates to
``services.pix_confirmation.confirm_pix``.

In development with ``payment_mock`` as the PIX adapter, there is no real
gateway to call us back. Instead, ``payment_mock.create_intent`` schedules
a ``mock_pix.confirm`` directive with ``available_at = now + delay``. When
the directive fires, this handler invokes the *same* ``confirm_pix`` that
the real webhook uses.

This is deliberate: there is one code path from "PIX authorized" to
"order.on_paid dispatched" in the entire system. Dev differs from prod
only in *who schedules the call*, never in *what runs*.
"""

from __future__ import annotations

import logging

from shopman.orderman.exceptions import DirectiveTerminalError
from shopman.orderman.models import Directive

logger = logging.getLogger(__name__)

MOCK_PIX_CONFIRM = "mock_pix.confirm"


class MockPixConfirmHandler:
    """Handler for ``mock_pix.confirm`` directives scheduled by the mock adapter."""

    topic = MOCK_PIX_CONFIRM

    def handle(self, *, message: Directive, ctx: dict) -> None:
        from shopman.shop.services.pix_confirmation import confirm_pix

        payload = message.payload or {}
        txid = payload.get("txid")
        if not txid:
            raise DirectiveTerminalError("missing txid in payload")

        confirm_pix(
            txid=txid,
            e2e_id=payload.get("e2e_id", ""),
            valor=payload.get("valor", ""),
        )


__all__ = ["MockPixConfirmHandler", "MOCK_PIX_CONFIRM"]
