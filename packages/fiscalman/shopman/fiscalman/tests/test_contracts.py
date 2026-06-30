"""Tests for the fiscal provider contract (pure Python, no DB)."""

from shopman.fiscalman.contracts import (
    FiscalBackend,
    FiscalCancellationResult,
    FiscalDocumentResult,
)


def test_document_result_defaults():
    result = FiscalDocumentResult(success=True, access_key="KEY")
    assert result.success is True
    assert result.access_key == "KEY"
    assert result.status == "pending"


def test_cancellation_result_defaults():
    result = FiscalCancellationResult(success=False, error_code="x")
    assert result.success is False
    assert result.protocol_number is None


def test_backend_is_runtime_checkable_protocol():
    class _Stub:
        def emit(self, *, reference, items, payment, customer=None, additional_info=None):
            return FiscalDocumentResult(success=True)

        def query_status(self, *, reference):
            return FiscalDocumentResult(success=True)

        def cancel(self, *, reference, reason):
            return FiscalCancellationResult(success=True)

    assert isinstance(_Stub(), FiscalBackend)

    class _NotABackend:
        pass

    assert not isinstance(_NotABackend(), FiscalBackend)
