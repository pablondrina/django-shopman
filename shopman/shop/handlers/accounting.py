"""
Accounting handler — cria conta a pagar.

Inline de shopman.accounting.handlers.
"""

from __future__ import annotations

import logging
from datetime import date

from shopman.orderman.models import Directive
from shopman.orderman.protocols import AccountingBackend
from shopman.shop.directives import ACCOUNTING_CREATE_PAYABLE

logger = logging.getLogger(__name__)


class PurchaseToPayableHandler:
    """Cria conta a pagar no backend contábil. Topic: accounting.create_payable"""

    topic = ACCOUNTING_CREATE_PAYABLE

    def __init__(self, backend: AccountingBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload

        reference = payload.get("reference")
        if reference:
            existing = self.backend.list_entries(reference=reference, limit=1)
            if existing:
                message.status = "done"
                message.save(update_fields=["status", "updated_at"])
                return

        result = self.backend.create_payable(
            description=payload["description"],
            amount_q=payload["amount_q"],
            due_date=date.fromisoformat(payload["due_date"]),
            category=payload["category"],
            supplier_name=payload.get("supplier_name"),
            reference=reference,
            notes=payload.get("notes"),
        )

        if result.success:
            message.status = "done"
            message.payload["entry_id"] = result.entry_id
            message.save(update_fields=["status", "payload", "updated_at"])
        else:
            message.status = "failed"
            message.last_error = f"Failed to create payable: {result.error_message}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            raise RuntimeError(f"Failed to create payable: {result.error_message}")


__all__ = ["PurchaseToPayableHandler"]
