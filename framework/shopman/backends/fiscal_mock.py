"""
Mock Fiscal Backend — Para desenvolvimento e testes.
"""

from __future__ import annotations

from shopman.ordering.protocols import (
    FiscalCancellationResult,
    FiscalDocumentResult,
)


class MockFiscalBackend:
    """Backend fiscal para testes e desenvolvimento."""

    def __init__(self, *, auto_authorize: bool = True):
        self.auto_authorize = auto_authorize
        self._documents: dict[str, dict] = {}

    def emit(
        self,
        *,
        reference: str,
        items: list[dict],
        customer: dict | None = None,
        payment: dict,
        additional_info: str | None = None,
    ) -> FiscalDocumentResult:
        """Emite documento fiscal mock."""
        if self.auto_authorize:
            doc = {
                "number": len(self._documents) + 1,
                "series": 1,
                "access_key": (
                    f"41260100000000000100650010000{len(self._documents) + 1:05d}"
                    f"1000000001"
                ),
                "status": "authorized",
                "danfe_url": f"/v2/nfce/{reference}.pdf",
                "qrcode_url": f"https://sefaz.example.com/qr/{reference}",
            }
            self._documents[reference] = doc
            return FiscalDocumentResult(
                success=True,
                document_id=reference,
                document_number=doc["number"],
                document_series=doc["series"],
                access_key=doc["access_key"],
                danfe_url=doc["danfe_url"],
                qrcode_url=doc["qrcode_url"],
                status="authorized",
            )
        return FiscalDocumentResult(success=False, status="pending")

    def query_status(self, *, reference: str) -> FiscalDocumentResult:
        """Consulta status mock."""
        doc = self._documents.get(reference)
        if doc:
            return FiscalDocumentResult(
                success=doc["status"] == "authorized",
                document_id=reference,
                document_number=doc["number"],
                document_series=doc["series"],
                access_key=doc["access_key"],
                danfe_url=doc.get("danfe_url"),
                qrcode_url=doc.get("qrcode_url"),
                status=doc["status"],
            )
        return FiscalDocumentResult(success=False, status="not_found")

    def cancel(self, *, reference: str, reason: str) -> FiscalCancellationResult:
        """Cancela documento fiscal mock."""
        if len(reason) < 15:
            return FiscalCancellationResult(
                success=False,
                error_message="Justificativa deve ter no mínimo 15 caracteres.",
            )
        if reference in self._documents:
            self._documents[reference]["status"] = "cancelled"
            return FiscalCancellationResult(
                success=True,
                protocol_number="mock_protocol_001",
                cancellation_date="2026-03-14T10:00:00",
            )
        return FiscalCancellationResult(
            success=False,
            error_message="Document not found",
        )
