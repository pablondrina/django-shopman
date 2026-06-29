"""Fiscal provider contract — what any fiscal backend must implement.

The fiscal domain owns this contract. Concrete provider integrations (e.g.
Focus NFe for NFC-e) are orchestrator-level adapters living in
``shopman/shop/adapters/`` — the same convention as the payment adapters
(``payment_efi``, ``payment_stripe``) — and implement this Protocol structurally.

Extension point: the system runs with no fiscal backend configured (handlers are
silent no-ops). Activate in production via ``SHOPMAN_FISCAL_ADAPTER`` in settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass
class FiscalDocumentResult:
    """Resultado da emissão de documento fiscal."""

    success: bool
    document_id: str | None = None
    document_number: int | None = None
    document_series: int | None = None
    access_key: str | None = None
    authorization_date: str | None = None
    protocol_number: str | None = None
    xml_url: str | None = None
    danfe_url: str | None = None
    qrcode_url: str | None = None
    status: str = "pending"  # pending, authorized, denied, cancelled
    error_code: str | None = None
    error_message: str | None = None


@dataclass
class FiscalCancellationResult:
    """Resultado do cancelamento de documento fiscal."""

    success: bool
    protocol_number: str | None = None
    cancellation_date: str | None = None
    error_code: str | None = None
    error_message: str | None = None


@runtime_checkable
class FiscalBackend(Protocol):
    """Protocol para backends fiscais (NFC-e, NF-e, etc.).

    Implementações de referência:
    - FocusNFeBackend: NFC-e via Focus NFe API (``shop/adapters/fiscal_focusnfe``).
    - MockFiscalBackend: para testes.
    """

    def emit(
        self,
        *,
        reference: str,
        items: list[dict],
        customer: dict | None = None,
        payment: dict,
        additional_info: str | None = None,
    ) -> FiscalDocumentResult:
        """Emite documento fiscal.

        Args:
            reference: Referência única (ex: ``Order.ref`` "ORD-2026-001").
            items: Itens [{description, ncm, cfop, quantity, unit, unit_price_q,
                total_q, tax_info}].
            customer: Consumidor (CPF opcional para NFC-e) {cpf?, name?, address?}.
            payment: {method (01=dinheiro, 03=crédito, 04=débito, 05=crédito_loja,
                15=boleto, 17=pix), amount_q}.
            additional_info: Informações complementares.
        """
        ...

    def query_status(self, *, reference: str) -> FiscalDocumentResult:
        """Consulta status de documento fiscal emitido."""
        ...

    def cancel(self, *, reference: str, reason: str) -> FiscalCancellationResult:
        """Cancela documento fiscal.

        Regras SEFA-PR (NFC-e): só dentro de **24h** da autorização e enquanto a
        mercadoria não circulou; motivo obrigatório (≥15 chars). O prazo é
        enforçado pela SEFAZ/provider, não por este código.
        """
        ...
