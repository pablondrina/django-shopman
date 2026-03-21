"""
Shopman Accounting Handlers — Handlers de diretiva para integração contábil.
"""

from __future__ import annotations

import logging
from datetime import date

from shopman.ordering.models import Directive
from shopman.ordering.protocols import AccountingBackend

logger = logging.getLogger(__name__)


class PurchaseToPayableHandler:
    """
    Quando Étienne confirma uma ordem de compra,
    cria conta a pagar no backend contábil.

    Topic: accounting.create_payable
    Payload: {
        description, amount_q, due_date, category,
        supplier_name?, reference (PO-xxx)
    }
    """

    topic = "accounting.create_payable"

    def __init__(self, backend: AccountingBackend):
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload

        # Idempotência: verifica se já criou via reference
        reference = payload.get("reference")
        if reference:
            existing = self.backend.list_entries(reference=reference, limit=1)
            if existing:
                logger.info(
                    "Payable already exists for reference %s", reference,
                )
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
            logger.info(
                "Payable created: entry_id=%s, reference=%s",
                result.entry_id, reference,
            )
            message.status = "done"
            message.payload["entry_id"] = result.entry_id
            message.save(update_fields=["status", "payload", "updated_at"])
        else:
            message.status = "failed"
            message.last_error = f"Failed to create payable: {result.error_message}"
            message.save(update_fields=["status", "last_error", "updated_at"])
            raise RuntimeError(
                f"Failed to create payable: {result.error_message}"
            )
