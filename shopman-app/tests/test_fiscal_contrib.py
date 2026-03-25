"""
Tests for contrib/fiscal module.

Covers:
- MockFiscalBackend
- FocusNFCeBackend (unit tests with mocked HTTP)
- NFCeEmitHandler
- NFCeCancelHandler
- Fiscal protocols (FiscalBackend, dataclasses)
- Monetary conversion _q → reais
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from django.test import TestCase

from channels.backends.fiscal_focus import FocusNFCeBackend
from channels.backends.fiscal_mock import MockFiscalBackend
from channels.handlers.fiscal import NFCeCancelHandler, NFCeEmitHandler
from channels.topics import FISCAL_CANCEL_NFCE, FISCAL_EMIT_NFCE
from shopman.ordering.models import Channel, Directive, Order, Session
from shopman.ordering.protocols import (
    FiscalBackend,
    FiscalCancellationResult,
    FiscalDocumentResult,
)


# =============================================================================
# Protocol Tests
# =============================================================================


class FiscalProtocolTests(TestCase):
    """Tests for fiscal protocol dataclasses."""

    def test_fiscal_document_result_defaults(self) -> None:
        """Should have sensible defaults."""
        result = FiscalDocumentResult(success=True)

        self.assertTrue(result.success)
        self.assertIsNone(result.document_id)
        self.assertIsNone(result.access_key)
        self.assertEqual(result.status, "pending")
        self.assertIsNone(result.error_message)

    def test_fiscal_document_result_full(self) -> None:
        """Should store all fields."""
        result = FiscalDocumentResult(
            success=True,
            document_id="REF-001",
            document_number=1234,
            document_series=1,
            access_key="41260100000000000100650010000012341000012345",
            authorization_date="2026-03-14T10:00:00",
            protocol_number="141260000012345",
            xml_url="/v2/nfce/REF-001.xml",
            danfe_url="/v2/nfce/REF-001.pdf",
            qrcode_url="https://sefaz.example.com/qr",
            status="authorized",
        )

        self.assertEqual(result.document_number, 1234)
        self.assertEqual(result.access_key, "41260100000000000100650010000012341000012345")
        self.assertEqual(result.status, "authorized")

    def test_fiscal_cancellation_result_defaults(self) -> None:
        """Should have sensible defaults."""
        result = FiscalCancellationResult(success=True)

        self.assertTrue(result.success)
        self.assertIsNone(result.protocol_number)
        self.assertIsNone(result.error_message)

    def test_mock_implements_fiscal_backend_protocol(self) -> None:
        """MockFiscalBackend should satisfy FiscalBackend protocol."""
        backend = MockFiscalBackend()
        self.assertIsInstance(backend, FiscalBackend)


# =============================================================================
# MockFiscalBackend Tests
# =============================================================================


class MockFiscalBackendTests(TestCase):
    """Tests for MockFiscalBackend."""

    def setUp(self) -> None:
        self.backend = MockFiscalBackend()

    def test_emit_auto_authorize(self) -> None:
        """Should return authorized result by default."""
        result = self.backend.emit(
            reference="ORD-001",
            items=[{
                "description": "Croissant",
                "quantity": 2,
                "unit_price_q": 1200,
                "total_q": 2400,
            }],
            payment={"method": "17", "amount_q": 2400},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "authorized")
        self.assertEqual(result.document_id, "ORD-001")
        self.assertIsNotNone(result.access_key)
        self.assertEqual(result.document_number, 1)
        self.assertEqual(result.document_series, 1)
        self.assertIsNotNone(result.danfe_url)
        self.assertIsNotNone(result.qrcode_url)

    def test_emit_without_auto_authorize(self) -> None:
        """Should return pending result when auto_authorize=False."""
        backend = MockFiscalBackend(auto_authorize=False)
        result = backend.emit(
            reference="ORD-002",
            items=[{"description": "Baguete", "quantity": 1, "unit_price_q": 1000, "total_q": 1000}],
            payment={"method": "01", "amount_q": 1000},
        )

        self.assertFalse(result.success)
        self.assertEqual(result.status, "pending")

    def test_emit_increments_document_number(self) -> None:
        """Should assign sequential document numbers."""
        self.backend.emit(
            reference="ORD-001",
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            payment={"amount_q": 100},
        )
        result = self.backend.emit(
            reference="ORD-002",
            items=[{"description": "B", "quantity": 1, "unit_price_q": 200, "total_q": 200}],
            payment={"amount_q": 200},
        )

        self.assertEqual(result.document_number, 2)

    def test_query_status_found(self) -> None:
        """Should return document info for emitted reference."""
        self.backend.emit(
            reference="ORD-001",
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            payment={"amount_q": 100},
        )

        result = self.backend.query_status(reference="ORD-001")

        self.assertTrue(result.success)
        self.assertEqual(result.status, "authorized")
        self.assertEqual(result.document_id, "ORD-001")

    def test_query_status_not_found(self) -> None:
        """Should return not_found for unknown reference."""
        result = self.backend.query_status(reference="UNKNOWN")

        self.assertFalse(result.success)
        self.assertEqual(result.status, "not_found")

    def test_cancel_success(self) -> None:
        """Should cancel emitted document."""
        self.backend.emit(
            reference="ORD-001",
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            payment={"amount_q": 100},
        )

        result = self.backend.cancel(
            reference="ORD-001",
            reason="Erro no pedido, cliente solicitou cancelamento",
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.protocol_number)

        # Verify status changed
        query = self.backend.query_status(reference="ORD-001")
        self.assertEqual(query.status, "cancelled")

    def test_cancel_not_found(self) -> None:
        """Should return error for unknown reference."""
        result = self.backend.cancel(
            reference="UNKNOWN",
            reason="Motivo com mais de 15 caracteres obrigatórios",
        )

        self.assertFalse(result.success)
        self.assertIn("not found", result.error_message.lower())

    def test_cancel_reason_too_short(self) -> None:
        """Should reject cancellation with reason < 15 chars."""
        self.backend.emit(
            reference="ORD-001",
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            payment={"amount_q": 100},
        )

        result = self.backend.cancel(
            reference="ORD-001",
            reason="curto",
        )

        self.assertFalse(result.success)
        self.assertIn("15 caracteres", result.error_message)


# =============================================================================
# FocusNFCeBackend Tests
# =============================================================================


class FocusNFCeBackendTests(TestCase):
    """Tests for FocusNFCeBackend (unit tests with mocked HTTP)."""

    def setUp(self) -> None:
        self.backend = FocusNFCeBackend(
            api_token="test_token",
            environment="homologation",
            cnpj="00000000000100",
            state_code="41",
        )

    def test_init_production_url(self) -> None:
        """Should use production URL for production environment."""
        backend = FocusNFCeBackend(api_token="x", environment="production")
        self.assertEqual(backend.base_url, FocusNFCeBackend.PRODUCTION_URL)

    def test_init_homologation_url(self) -> None:
        """Should use homologation URL for non-production environment."""
        self.assertEqual(self.backend.base_url, FocusNFCeBackend.HOMOLOGATION_URL)

    def test_build_nfce_payload_basic(self) -> None:
        """Should build correct NFC-e payload from items."""
        payload = self.backend._build_nfce_payload(
            items=[{
                "sku": "CRO-001",
                "description": "Croissant Clássico",
                "quantity": 2,
                "unit_price_q": 1200,
                "total_q": 2400,
            }],
            customer=None,
            payment={"method": "17", "amount_q": 2400},
            additional_info=None,
        )

        self.assertEqual(payload["natureza_operacao"], "Venda ao consumidor final")
        self.assertEqual(payload["tipo_documento"], 1)
        self.assertEqual(len(payload["items"]), 1)

        item = payload["items"][0]
        self.assertEqual(item["codigo_produto"], "CRO-001")
        self.assertEqual(item["descricao"], "Croissant Clássico")
        self.assertEqual(item["quantidade_comercial"], 2.0)
        self.assertEqual(item["valor_unitario_comercial"], 12.00)
        self.assertEqual(item["valor_bruto"], 24.00)
        self.assertEqual(item["icms_situacao_tributaria"], "102")
        self.assertEqual(item["pis_situacao_tributaria"], "49")
        self.assertEqual(item["cofins_situacao_tributaria"], "49")

        pagamento = payload["formas_pagamento"][0]
        self.assertEqual(pagamento["forma_pagamento"], "17")
        self.assertEqual(pagamento["valor_pagamento"], 24.00)

    def test_build_nfce_payload_with_customer_cpf(self) -> None:
        """Should include CPF when customer provides it."""
        payload = self.backend._build_nfce_payload(
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            customer={"cpf": "123.456.789-00", "name": "João"},
            payment={"amount_q": 100},
            additional_info=None,
        )

        self.assertEqual(payload["cpf"], "12345678900")
        self.assertEqual(payload["nome"], "João")

    def test_build_nfce_payload_with_additional_info(self) -> None:
        """Should include additional info when provided."""
        payload = self.backend._build_nfce_payload(
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            customer=None,
            payment={"amount_q": 100},
            additional_info="Pedido via delivery",
        )

        self.assertEqual(
            payload["informacoes_adicionais_contribuinte"],
            "Pedido via delivery",
        )

    def test_build_nfce_payload_monetary_conversion(self) -> None:
        """Should convert _q (centavos) to reais correctly."""
        payload = self.backend._build_nfce_payload(
            items=[{
                "description": "Pão Francês",
                "quantity": 5,
                "unit_price_q": 150,  # R$ 1,50
                "total_q": 750,  # R$ 7,50
            }],
            customer=None,
            payment={"amount_q": 750},
            additional_info=None,
        )

        item = payload["items"][0]
        self.assertEqual(item["valor_unitario_comercial"], 1.50)
        self.assertEqual(item["valor_bruto"], 7.50)

        pagamento = payload["formas_pagamento"][0]
        self.assertEqual(pagamento["valor_pagamento"], 7.50)

    def test_build_nfce_payload_uses_defaults(self) -> None:
        """Should use default NCM and CFOP when not provided per item."""
        payload = self.backend._build_nfce_payload(
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            customer=None,
            payment={"amount_q": 100},
            additional_info=None,
        )

        item = payload["items"][0]
        self.assertEqual(item["codigo_ncm"], "19059090")
        self.assertEqual(item["cfop"], "5102")

    def test_build_nfce_payload_item_overrides(self) -> None:
        """Should allow per-item NCM, CFOP, and tax overrides."""
        payload = self.backend._build_nfce_payload(
            items=[{
                "description": "Café",
                "quantity": 1,
                "unit_price_q": 500,
                "total_q": 500,
                "ncm": "09011110",
                "cfop": "6102",
                "icms_cst": "500",
                "pis_cst": "01",
                "cofins_cst": "01",
            }],
            customer=None,
            payment={"amount_q": 500},
            additional_info=None,
        )

        item = payload["items"][0]
        self.assertEqual(item["codigo_ncm"], "09011110")
        self.assertEqual(item["cfop"], "6102")
        self.assertEqual(item["icms_situacao_tributaria"], "500")
        self.assertEqual(item["pis_situacao_tributaria"], "01")
        self.assertEqual(item["cofins_situacao_tributaria"], "01")

    @patch("channels.backends.fiscal_focus.urlopen")
    def test_emit_success(self, mock_urlopen) -> None:
        """Should emit NFC-e and return authorized result."""
        # First call: POST emit (processando)
        # Second call: GET query_status (autorizado)
        mock_responses = [
            MagicMock(
                read=MagicMock(return_value=json.dumps(
                    {"status": "processando_autorizacao"}
                ).encode()),
                __enter__=MagicMock(),
                __exit__=MagicMock(return_value=False),
            ),
            MagicMock(
                read=MagicMock(return_value=json.dumps({
                    "status": "autorizado",
                    "numero": 1234,
                    "serie": 1,
                    "chave_nfe": "41260100000000000100650010000012341000012345",
                    "protocolo": "141260000012345",
                    "data_emissao": "2026-03-14T10:00:00",
                    "caminho_xml_nota_fiscal": "/v2/nfce/ORD-001.xml",
                    "caminho_danfe": "/v2/nfce/ORD-001.pdf",
                    "url_qrcode": "https://sefaz.example.com/qr",
                }).encode()),
                __enter__=MagicMock(),
                __exit__=MagicMock(return_value=False),
            ),
        ]
        for m in mock_responses:
            m.__enter__.return_value = m
        mock_urlopen.side_effect = mock_responses

        result = self.backend.emit(
            reference="ORD-001",
            items=[{"description": "Croissant", "quantity": 2, "unit_price_q": 1200, "total_q": 2400}],
            payment={"method": "17", "amount_q": 2400},
        )

        self.assertTrue(result.success)
        self.assertEqual(result.status, "authorized")
        self.assertEqual(result.document_number, 1234)
        self.assertEqual(result.access_key, "41260100000000000100650010000012341000012345")
        self.assertEqual(result.danfe_url, "/v2/nfce/ORD-001.pdf")

    @patch("channels.backends.fiscal_focus.urlopen")
    def test_emit_denied(self, mock_urlopen) -> None:
        """Should return denied result when Focus API rejects."""
        mock_response = MagicMock(
            read=MagicMock(return_value=json.dumps({
                "status": "erro_autorizacao",
                "codigo": "100",
                "mensagem": "Dados inválidos",
            }).encode()),
            __enter__=MagicMock(),
            __exit__=MagicMock(return_value=False),
        )
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = self.backend.emit(
            reference="ORD-002",
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            payment={"amount_q": 100},
        )

        self.assertFalse(result.success)
        self.assertEqual(result.status, "denied")

    @patch("channels.backends.fiscal_focus.urlopen")
    def test_emit_exception(self, mock_urlopen) -> None:
        """Should handle network errors gracefully."""
        mock_urlopen.side_effect = Exception("Connection timeout")

        result = self.backend.emit(
            reference="ORD-003",
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            payment={"amount_q": 100},
        )

        self.assertFalse(result.success)
        self.assertEqual(result.status, "error")
        self.assertIn("Connection timeout", result.error_message)

    @patch("channels.backends.fiscal_focus.urlopen")
    def test_cancel_success(self, mock_urlopen) -> None:
        """Should cancel NFC-e successfully."""
        mock_response = MagicMock(
            read=MagicMock(return_value=json.dumps({
                "status": "cancelado",
                "protocolo": "141260000012346",
                "data_evento": "2026-03-14T10:30:00",
            }).encode()),
            __enter__=MagicMock(),
            __exit__=MagicMock(return_value=False),
        )
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = self.backend.cancel(
            reference="ORD-001",
            reason="Erro no pedido, cliente solicitou cancelamento",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.protocol_number, "141260000012346")
        self.assertEqual(result.cancellation_date, "2026-03-14T10:30:00")

    def test_cancel_reason_too_short(self) -> None:
        """Should reject reason with < 15 characters (SEFAZ rule)."""
        result = self.backend.cancel(
            reference="ORD-001",
            reason="curto",
        )

        self.assertFalse(result.success)
        self.assertIn("15 caracteres", result.error_message)


# =============================================================================
# NFCeEmitHandler Tests
# =============================================================================


class NFCeEmitHandlerTests(TestCase):
    """Tests for NFCeEmitHandler directive handler."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(ref="pdv", name="PDV")
        self.session = Session.objects.create(
            session_key="S-001", channel=self.channel,
        )
        self.order = Order.objects.create(
            ref="ORD-FISCAL-001",
            channel=self.channel,
            session_key="S-001",
            total_q=2400,
            data={},
        )
        self.backend = MockFiscalBackend()
        self.handler = NFCeEmitHandler(backend=self.backend)

    def test_emit_success_stores_metadata(self) -> None:
        """Should emit NFC-e and store access_key in Order.data."""
        directive = Directive.objects.create(
            topic=FISCAL_EMIT_NFCE,
            payload={
                "order_ref": "ORD-FISCAL-001",
                "items": [{
                    "description": "Croissant",
                    "quantity": 2,
                    "unit_price_q": 1200,
                    "total_q": 2400,
                }],
                "payment": {"method": "17", "amount_q": 2400},
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        self.order.refresh_from_db()
        self.assertIsNotNone(self.order.data.get("nfce_access_key"))
        self.assertEqual(self.order.data["nfce_number"], 1)
        self.assertIsNotNone(self.order.data.get("nfce_danfe_url"))
        self.assertIsNotNone(self.order.data.get("nfce_qrcode_url"))

    def test_emit_idempotent(self) -> None:
        """Should skip if NFC-e already emitted (access_key exists)."""
        self.order.data["nfce_access_key"] = "existing_key"
        self.order.save(update_fields=["data"])

        directive = Directive.objects.create(
            topic=FISCAL_EMIT_NFCE,
            payload={
                "order_ref": "ORD-FISCAL-001",
                "items": [{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
                "payment": {"amount_q": 100},
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        # Should not have emitted (no documents in backend)
        self.assertEqual(len(self.backend._documents), 0)

    def test_emit_order_not_found(self) -> None:
        """Should fail directive when order doesn't exist."""
        directive = Directive.objects.create(
            topic=FISCAL_EMIT_NFCE,
            payload={
                "order_ref": "NONEXISTENT",
                "items": [{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
                "payment": {"amount_q": 100},
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")
        self.assertIn("Order not found", directive.last_error)

    def test_emit_failure_raises(self) -> None:
        """Should raise RuntimeError when emission fails."""
        backend = MockFiscalBackend(auto_authorize=False)
        handler = NFCeEmitHandler(backend=backend)

        directive = Directive.objects.create(
            topic=FISCAL_EMIT_NFCE,
            payload={
                "order_ref": "ORD-FISCAL-001",
                "items": [{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
                "payment": {"amount_q": 100},
            },
        )

        with self.assertRaises(RuntimeError):
            handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")


# =============================================================================
# NFCeCancelHandler Tests
# =============================================================================


class NFCeCancelHandlerTests(TestCase):
    """Tests for NFCeCancelHandler directive handler."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(ref="pdv-c", name="PDV Cancel")
        self.order = Order.objects.create(
            ref="ORD-CANCEL-001",
            channel=self.channel,
            session_key="S-CANCEL-001",
            total_q=2400,
            data={},
        )
        self.backend = MockFiscalBackend()
        self.handler = NFCeCancelHandler(backend=self.backend)

        # Pre-emit a document
        self.backend.emit(
            reference="ORD-CANCEL-001",
            items=[{"description": "A", "quantity": 1, "unit_price_q": 100, "total_q": 100}],
            payment={"amount_q": 100},
        )

    def test_cancel_success(self) -> None:
        """Should cancel NFC-e and update Order.data."""
        directive = Directive.objects.create(
            topic=FISCAL_CANCEL_NFCE,
            payload={
                "order_ref": "ORD-CANCEL-001",
                "reason": "Erro no pedido, cliente solicitou cancelamento",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        self.order.refresh_from_db()
        self.assertTrue(self.order.data.get("nfce_cancelled"))
        self.assertIsNotNone(self.order.data.get("nfce_cancellation_protocol"))

    def test_cancel_idempotent(self) -> None:
        """Should skip if already cancelled."""
        self.order.data["nfce_cancelled"] = True
        self.order.save(update_fields=["data"])

        directive = Directive.objects.create(
            topic=FISCAL_CANCEL_NFCE,
            payload={
                "order_ref": "ORD-CANCEL-001",
                "reason": "Motivo com mais de 15 caracteres obrigatórios",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

    def test_cancel_order_not_found(self) -> None:
        """Should fail directive when order doesn't exist."""
        directive = Directive.objects.create(
            topic=FISCAL_CANCEL_NFCE,
            payload={
                "order_ref": "NONEXISTENT",
                "reason": "Motivo com mais de 15 caracteres obrigatórios",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "failed")

    def test_cancel_failure_raises(self) -> None:
        """Should raise RuntimeError when cancellation fails (reason too short)."""
        # Use a fresh backend with no documents to trigger failure
        backend = MockFiscalBackend()
        handler = NFCeCancelHandler(backend=backend)

        directive = Directive.objects.create(
            topic=FISCAL_CANCEL_NFCE,
            payload={
                "order_ref": "ORD-CANCEL-001",
                "reason": "Motivo com mais de 15 caracteres obrigatórios",
            },
        )

        with self.assertRaises(RuntimeError):
            handler.handle(message=directive, ctx={})
