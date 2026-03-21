"""
Tests for contrib/accounting module.

Covers:
- MockAccountingBackend
- ContaAzulBackend (unit tests with mocked HTTP)
- ContaAzulTokenManager
- PurchaseToPayableHandler
- Accounting protocols (AccountingBackend, dataclasses)
- REST API views (CashFlow, Accounts, Entries, CreatePayable)
- Monetary conversion _q ↔ reais
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from shopman.accounting.backends.contaazul import (
    ContaAzulBackend,
    ContaAzulTokenManager,
)
from shopman.accounting.backends.mock import MockAccountingBackend
from shopman.accounting.handlers import PurchaseToPayableHandler
from shopman.ordering.models import Channel, Directive
from shopman.ordering.protocols import (
    AccountEntry,
    AccountingBackend,
    AccountsSummary,
    CashFlowSummary,
    CreateEntryResult,
)


# =============================================================================
# Protocol Tests
# =============================================================================


class AccountingProtocolTests(TestCase):
    """Tests for accounting protocol dataclasses."""

    def test_account_entry_defaults(self) -> None:
        """Should have sensible defaults."""
        entry = AccountEntry(
            entry_id="E-001",
            description="Test",
            amount_q=1000,
            type="revenue",
            category="vendas",
            date=date(2026, 3, 14),
        )

        self.assertEqual(entry.status, "pending")
        self.assertIsNone(entry.due_date)
        self.assertIsNone(entry.paid_date)
        self.assertEqual(entry.metadata, {})

    def test_cash_flow_summary_defaults(self) -> None:
        """Should have empty category dicts by default."""
        summary = CashFlowSummary(
            period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31),
            total_revenue_q=100000,
            total_expenses_q=50000,
            net_q=50000,
            balance_q=50000,
        )

        self.assertEqual(summary.revenue_by_category, {})
        self.assertEqual(summary.expenses_by_category, {})

    def test_accounts_summary_defaults(self) -> None:
        """Should have empty lists by default."""
        summary = AccountsSummary(
            total_receivable_q=0,
            total_payable_q=0,
            overdue_receivable_q=0,
            overdue_payable_q=0,
        )

        self.assertEqual(summary.receivables, [])
        self.assertEqual(summary.payables, [])

    def test_create_entry_result(self) -> None:
        """Should store success and entry_id."""
        result = CreateEntryResult(success=True, entry_id="E-001")
        self.assertTrue(result.success)
        self.assertEqual(result.entry_id, "E-001")

    def test_mock_implements_accounting_backend_protocol(self) -> None:
        """MockAccountingBackend should satisfy AccountingBackend protocol."""
        backend = MockAccountingBackend()
        self.assertIsInstance(backend, AccountingBackend)


# =============================================================================
# MockAccountingBackend Tests
# =============================================================================


class MockAccountingBackendTests(TestCase):
    """Tests for MockAccountingBackend."""

    def setUp(self) -> None:
        self.backend = MockAccountingBackend()

    def test_create_payable(self) -> None:
        """Should create payable entry."""
        result = self.backend.create_payable(
            description="Farinha de trigo 50kg",
            amount_q=50000,
            due_date=date(2026, 3, 20),
            category="insumos",
            supplier_name="Moinho Sul",
            reference="PO-2026-001",
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.entry_id)
        self.assertTrue(result.entry_id.startswith("mock_pay_"))

    def test_create_receivable(self) -> None:
        """Should create receivable entry."""
        result = self.backend.create_receivable(
            description="Venda balcão",
            amount_q=15000,
            due_date=date(2026, 3, 14),
            category="vendas_balcao",
            reference="ORD-2026-001",
        )

        self.assertTrue(result.success)
        self.assertIsNotNone(result.entry_id)
        self.assertTrue(result.entry_id.startswith("mock_rec_"))

    def test_get_cash_flow(self) -> None:
        """Should calculate cash flow from entries."""
        self.backend.create_receivable(
            description="Venda 1",
            amount_q=10000,
            due_date=date(2026, 3, 10),
            category="vendas",
        )
        self.backend.create_receivable(
            description="Venda 2",
            amount_q=15000,
            due_date=date(2026, 3, 15),
            category="vendas",
        )
        self.backend.create_payable(
            description="Despesa",
            amount_q=5000,
            due_date=date(2026, 3, 12),
            category="insumos",
        )

        summary = self.backend.get_cash_flow(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

        self.assertEqual(summary.total_revenue_q, 25000)
        self.assertEqual(summary.total_expenses_q, 5000)
        self.assertEqual(summary.net_q, 20000)
        self.assertEqual(summary.revenue_by_category, {"vendas": 25000})
        self.assertEqual(summary.expenses_by_category, {"insumos": 5000})

    def test_get_cash_flow_filters_by_date(self) -> None:
        """Should only include entries within the period."""
        self.backend.create_receivable(
            description="In range",
            amount_q=10000,
            due_date=date(2026, 3, 15),
            category="vendas",
        )
        self.backend.create_receivable(
            description="Out of range",
            amount_q=99999,
            due_date=date(2026, 4, 15),
            category="vendas",
        )

        summary = self.backend.get_cash_flow(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

        self.assertEqual(summary.total_revenue_q, 10000)

    def test_get_accounts_summary(self) -> None:
        """Should summarize pending receivables and payables."""
        self.backend.create_receivable(
            description="Receivable pending",
            amount_q=10000,
            due_date=date(2026, 3, 10),
            category="vendas",
        )
        self.backend.create_payable(
            description="Payable pending",
            amount_q=5000,
            due_date=date(2026, 3, 5),
            category="insumos",
        )

        summary = self.backend.get_accounts_summary(as_of=date(2026, 3, 14))

        self.assertEqual(summary.total_receivable_q, 10000)
        self.assertEqual(summary.total_payable_q, 5000)
        self.assertEqual(summary.overdue_receivable_q, 10000)
        self.assertEqual(summary.overdue_payable_q, 5000)
        self.assertEqual(len(summary.receivables), 1)
        self.assertEqual(len(summary.payables), 1)

    def test_get_accounts_summary_excludes_paid(self) -> None:
        """Should only include pending entries in summary."""
        result = self.backend.create_receivable(
            description="Will be paid",
            amount_q=10000,
            due_date=date(2026, 3, 10),
            category="vendas",
        )
        self.backend.mark_as_paid(entry_id=result.entry_id)

        summary = self.backend.get_accounts_summary(as_of=date(2026, 3, 14))

        self.assertEqual(summary.total_receivable_q, 0)
        self.assertEqual(len(summary.receivables), 0)

    def test_list_entries_all(self) -> None:
        """Should list all entries."""
        self.backend.create_receivable(
            description="R1", amount_q=100, due_date=date(2026, 3, 10), category="vendas",
        )
        self.backend.create_payable(
            description="P1", amount_q=200, due_date=date(2026, 3, 15), category="insumos",
        )

        entries = self.backend.list_entries()

        self.assertEqual(len(entries), 2)

    def test_list_entries_filter_by_type(self) -> None:
        """Should filter by type."""
        self.backend.create_receivable(
            description="R1", amount_q=100, due_date=date(2026, 3, 10), category="vendas",
        )
        self.backend.create_payable(
            description="P1", amount_q=200, due_date=date(2026, 3, 15), category="insumos",
        )

        entries = self.backend.list_entries(type="revenue")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].type, "revenue")

    def test_list_entries_filter_by_date_range(self) -> None:
        """Should filter by date range."""
        self.backend.create_receivable(
            description="In", amount_q=100, due_date=date(2026, 3, 10), category="vendas",
        )
        self.backend.create_receivable(
            description="Out", amount_q=200, due_date=date(2026, 4, 10), category="vendas",
        )

        entries = self.backend.list_entries(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

        self.assertEqual(len(entries), 1)

    def test_list_entries_filter_by_reference(self) -> None:
        """Should filter by reference."""
        self.backend.create_payable(
            description="PO", amount_q=100, due_date=date(2026, 3, 10),
            category="insumos", reference="PO-001",
        )
        self.backend.create_payable(
            description="PO2", amount_q=200, due_date=date(2026, 3, 15),
            category="insumos", reference="PO-002",
        )

        entries = self.backend.list_entries(reference="PO-001")

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].reference, "PO-001")

    def test_list_entries_pagination(self) -> None:
        """Should support limit and offset."""
        for i in range(5):
            self.backend.create_receivable(
                description=f"R{i}", amount_q=100 * (i + 1),
                due_date=date(2026, 3, 10 + i), category="vendas",
            )

        page1 = self.backend.list_entries(limit=2, offset=0)
        page2 = self.backend.list_entries(limit=2, offset=2)

        self.assertEqual(len(page1), 2)
        self.assertEqual(len(page2), 2)

    def test_mark_as_paid_success(self) -> None:
        """Should mark entry as paid."""
        result = self.backend.create_payable(
            description="Test", amount_q=1000,
            due_date=date(2026, 3, 15), category="insumos",
        )

        pay_result = self.backend.mark_as_paid(
            entry_id=result.entry_id,
            paid_date=date(2026, 3, 14),
        )

        self.assertTrue(pay_result.success)

        entries = self.backend.list_entries(status="paid")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].paid_date, date(2026, 3, 14))

    def test_mark_as_paid_not_found(self) -> None:
        """Should return error for unknown entry."""
        result = self.backend.mark_as_paid(entry_id="NONEXISTENT")

        self.assertFalse(result.success)
        self.assertIn("not found", result.error_message.lower())

    def test_monetary_values_in_centavos(self) -> None:
        """All monetary values should be in centavos (_q convention)."""
        self.backend.create_receivable(
            description="R$ 150,00",
            amount_q=15000,  # 150 reais = 15000 centavos
            due_date=date(2026, 3, 14),
            category="vendas",
        )

        entries = self.backend.list_entries()
        self.assertEqual(entries[0].amount_q, 15000)

        summary = self.backend.get_cash_flow(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )
        self.assertEqual(summary.total_revenue_q, 15000)


# =============================================================================
# ContaAzulTokenManager Tests
# =============================================================================


class ContaAzulTokenManagerTests(TestCase):
    """Tests for ContaAzulTokenManager."""

    def setUp(self) -> None:
        self.manager = ContaAzulTokenManager(
            client_id="test_client_id",
            client_secret="test_client_secret",
            redirect_uri="https://example.com/callback",
        )

    @patch("shopman.accounting.backends.contaazul.urlopen")
    def test_authorize_exchanges_code_for_tokens(self, mock_urlopen) -> None:
        """Should exchange authorization code for tokens."""
        mock_response = MagicMock(
            read=MagicMock(return_value=json.dumps({
                "access_token": "access_123",
                "refresh_token": "refresh_456",
                "expires_in": 3600,
            }).encode()),
            __enter__=MagicMock(),
            __exit__=MagicMock(return_value=False),
        )
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        token_data = self.manager.authorize("auth_code_xyz")

        self.assertEqual(token_data["access_token"], "access_123")
        self.assertEqual(token_data["refresh_token"], "refresh_456")

    def test_refresh_without_token_raises(self) -> None:
        """Should raise when no refresh token available."""
        with self.assertRaises(RuntimeError) as ctx:
            self.manager._refresh_token(None)

        self.assertIn("refresh token", str(ctx.exception).lower())


# =============================================================================
# ContaAzulBackend Tests
# =============================================================================


class ContaAzulBackendTests(TestCase):
    """Tests for ContaAzulBackend (unit tests with mocked HTTP)."""

    def setUp(self) -> None:
        self.token_manager = MagicMock()
        self.token_manager.get_access_token.return_value = "test_token"
        self.backend = ContaAzulBackend(
            token_manager=self.token_manager,
            category_map={
                "insumos": "cat-uuid-insumos",
                "vendas_balcao": "cat-uuid-vendas",
            },
        )

    @patch("shopman.accounting.backends.contaazul.urlopen")
    def test_get_cash_flow(self, mock_urlopen) -> None:
        """Should calculate cash flow from API responses."""
        sales_response = json.dumps([
            {"total": 100.00, "status": "COMMITTED", "category": {"name": "Vendas"}},
            {"total": 50.00, "status": "COMMITTED", "category": {"name": "Vendas"}},
        ]).encode()
        bills_response = json.dumps([
            {"value": 30.00, "status": "PAID", "category": {"name": "Insumos"}},
        ]).encode()

        responses = []
        for data in [sales_response, bills_response]:
            mock = MagicMock(
                read=MagicMock(return_value=data),
                __enter__=MagicMock(),
                __exit__=MagicMock(return_value=False),
            )
            mock.__enter__.return_value = mock
            responses.append(mock)
        mock_urlopen.side_effect = responses

        result = self.backend.get_cash_flow(
            start_date=date(2026, 3, 1),
            end_date=date(2026, 3, 31),
        )

        self.assertEqual(result.total_revenue_q, 15000)  # R$ 150,00
        self.assertEqual(result.total_expenses_q, 3000)  # R$ 30,00
        self.assertEqual(result.net_q, 12000)
        self.assertEqual(result.revenue_by_category, {"Vendas": 15000})
        self.assertEqual(result.expenses_by_category, {"Insumos": 3000})

    @patch("shopman.accounting.backends.contaazul.urlopen")
    def test_get_accounts_summary(self, mock_urlopen) -> None:
        """Should return accounts summary from API."""
        receivables_response = json.dumps([
            {
                "id": "R-1", "value": 200.00,
                "status": "AWAITING",
                "due_date": "2026-03-05",
                "document": "ORD-001",
                "category": {"name": "Vendas"},
                "customer": {"name": "João"},
            },
        ]).encode()
        bills_response = json.dumps([
            {
                "id": "B-1", "value": 100.00, "due_date": "2026-03-08",
                "status": "AWAITING", "document": "PO-001",
                "category": {"name": "Insumos"},
                "supplier": {"name": "Moinho"},
            },
        ]).encode()

        responses = []
        for data in [receivables_response, bills_response]:
            mock = MagicMock(
                read=MagicMock(return_value=data),
                __enter__=MagicMock(),
                __exit__=MagicMock(return_value=False),
            )
            mock.__enter__.return_value = mock
            responses.append(mock)
        mock_urlopen.side_effect = responses

        result = self.backend.get_accounts_summary(as_of=date(2026, 3, 14))

        self.assertEqual(result.total_receivable_q, 20000)
        self.assertEqual(result.total_payable_q, 10000)
        self.assertEqual(result.overdue_receivable_q, 20000)
        self.assertEqual(result.overdue_payable_q, 10000)

    @patch("shopman.accounting.backends.contaazul.urlopen")
    def test_create_payable_success(self, mock_urlopen) -> None:
        """Should create payable via Conta Azul API."""
        # Two calls: 1) resolve supplier, 2) create bill
        supplier_response = MagicMock(
            read=MagicMock(return_value=json.dumps(
                [{"id": "supplier-uuid-1", "name": "Moinho Sul"}]
            ).encode()),
            __enter__=MagicMock(),
            __exit__=MagicMock(return_value=False),
        )
        supplier_response.__enter__.return_value = supplier_response

        bill_response = MagicMock(
            read=MagicMock(return_value=json.dumps({"id": "bill-uuid-123"}).encode()),
            __enter__=MagicMock(),
            __exit__=MagicMock(return_value=False),
        )
        bill_response.__enter__.return_value = bill_response

        mock_urlopen.side_effect = [supplier_response, bill_response]

        result = self.backend.create_payable(
            description="Farinha 50kg",
            amount_q=50000,
            due_date=date(2026, 3, 20),
            category="insumos",
            supplier_name="Moinho Sul",
            reference="PO-001",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.entry_id, "bill-uuid-123")

    def test_create_payable_unmapped_category(self) -> None:
        """Should return error for unmapped category."""
        result = self.backend.create_payable(
            description="Test",
            amount_q=1000,
            due_date=date(2026, 3, 20),
            category="unknown_category",
        )

        self.assertFalse(result.success)
        self.assertIn("não mapeada", result.error_message)

    @patch("shopman.accounting.backends.contaazul.urlopen")
    def test_create_payable_monetary_conversion(self, mock_urlopen) -> None:
        """Should convert _q to reais when sending to API."""
        mock_response = MagicMock(
            read=MagicMock(return_value=json.dumps({"id": "x"}).encode()),
            __enter__=MagicMock(),
            __exit__=MagicMock(return_value=False),
        )
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        self.backend.create_payable(
            description="Test",
            amount_q=15050,  # R$ 150,50
            due_date=date(2026, 3, 20),
            category="insumos",
        )

        # Check the payload sent to the API
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        sent_data = json.loads(request_obj.data.decode("utf-8"))
        self.assertEqual(sent_data["value"], 150.50)

    @patch("shopman.accounting.backends.contaazul.urlopen")
    def test_create_receivable_success(self, mock_urlopen) -> None:
        """Should create receivable via Conta Azul API."""
        mock_response = MagicMock(
            read=MagicMock(return_value=json.dumps({"id": "rec-uuid-456"}).encode()),
            __enter__=MagicMock(),
            __exit__=MagicMock(return_value=False),
        )
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        result = self.backend.create_receivable(
            description="Venda balcão",
            amount_q=3500,
            due_date=date(2026, 3, 14),
            category="vendas_balcao",
            reference="ORD-001",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.entry_id, "rec-uuid-456")

    def test_map_status(self) -> None:
        """Should map internal status to Conta Azul status."""
        self.assertEqual(self.backend._map_status("pending"), "AWAITING")
        self.assertEqual(self.backend._map_status("paid"), "PAID")
        self.assertEqual(self.backend._map_status("overdue"), "AWAITING")

    def test_to_entry_revenue(self) -> None:
        """Should convert revenue API response to AccountEntry."""
        raw = {
            "id": "S-1",
            "number": 1234,
            "total": 150.00,
            "emission": "2026-03-14",
            "status": "COMMITTED",
            "category": {"name": "Vendas Balcão"},
            "customer": {"name": "João"},
        }

        entry = self.backend._to_entry(raw, "revenue")

        self.assertEqual(entry.entry_id, "S-1")
        self.assertEqual(entry.amount_q, 15000)
        self.assertEqual(entry.type, "revenue")
        self.assertEqual(entry.status, "paid")
        self.assertEqual(entry.customer_name, "João")

    def test_to_entry_expense(self) -> None:
        """Should convert expense API response to AccountEntry."""
        raw = {
            "id": "B-1",
            "value": 500.00,
            "due_date": "2026-03-20",
            "status": "AWAITING",
            "document": "PO-001",
            "notes": "Farinha de trigo",
            "category": {"name": "Insumos"},
            "supplier": {"name": "Moinho Sul"},
        }

        entry = self.backend._to_entry(raw, "expense")

        self.assertEqual(entry.entry_id, "B-1")
        self.assertEqual(entry.amount_q, 50000)
        self.assertEqual(entry.type, "expense")
        self.assertEqual(entry.status, "pending")
        self.assertEqual(entry.supplier_name, "Moinho Sul")
        self.assertEqual(entry.due_date, date(2026, 3, 20))

    def test_group_by_category(self) -> None:
        """Should group amounts by category name."""
        items = [
            {"total": 100.00, "category": {"name": "Vendas"}},
            {"total": 50.00, "category": {"name": "Vendas"}},
            {"total": 30.00, "category": {"name": "Delivery"}},
        ]

        result = self.backend._group_by_category(items, "revenue")

        self.assertEqual(result, {"Vendas": 15000, "Delivery": 3000})


# =============================================================================
# PurchaseToPayableHandler Tests
# =============================================================================


class PurchaseToPayableHandlerTests(TestCase):
    """Tests for PurchaseToPayableHandler directive handler."""

    def setUp(self) -> None:
        self.channel = Channel.objects.create(ref="accounting-test", name="Accounting Test")
        self.backend = MockAccountingBackend()
        self.handler = PurchaseToPayableHandler(backend=self.backend)

    def test_create_payable_success(self) -> None:
        """Should create payable and mark directive as done."""
        directive = Directive.objects.create(
            topic="accounting.create_payable",
            payload={
                "description": "Farinha de trigo 50kg",
                "amount_q": 50000,
                "due_date": "2026-03-20",
                "category": "insumos",
                "supplier_name": "Moinho Sul",
                "reference": "PO-2026-001",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")
        self.assertIsNotNone(directive.payload.get("entry_id"))

    def test_create_payable_idempotent(self) -> None:
        """Should skip if payable with same reference already exists."""
        # Create first
        self.backend.create_payable(
            description="Existing",
            amount_q=50000,
            due_date=date(2026, 3, 20),
            category="insumos",
            reference="PO-2026-001",
        )

        directive = Directive.objects.create(
            topic="accounting.create_payable",
            payload={
                "description": "Duplicate",
                "amount_q": 50000,
                "due_date": "2026-03-20",
                "category": "insumos",
                "reference": "PO-2026-001",
            },
        )

        self.handler.handle(message=directive, ctx={})

        directive.refresh_from_db()
        self.assertEqual(directive.status, "done")

        # Should only have 1 entry (the original)
        entries = self.backend.list_entries(reference="PO-2026-001")
        self.assertEqual(len(entries), 1)


# =============================================================================
# REST API Tests
# =============================================================================


class AccountingAPITests(TestCase):
    """Tests for accounting REST API views."""

    def setUp(self) -> None:
        from django.contrib.auth import get_user_model
        from shopman.accounting.api.views import set_accounting_backend

        User = get_user_model()
        self.user = User.objects.create_user(
            username="anais", password="testpass123",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.backend = MockAccountingBackend()
        set_accounting_backend(self.backend)

        # Seed some data
        self.backend.create_receivable(
            description="Venda 1",
            amount_q=10000,
            due_date=date(2026, 3, 10),
            category="vendas",
        )
        self.backend.create_payable(
            description="Despesa 1",
            amount_q=5000,
            due_date=date(2026, 3, 5),
            category="insumos",
            reference="PO-001",
        )

    def tearDown(self) -> None:
        from shopman.accounting.api.views import set_accounting_backend
        set_accounting_backend(None)

    def test_cash_flow_view(self) -> None:
        """GET /api/accounting/cash-flow/ should return cash flow summary."""
        response = self.client.get(
            "/api/accounting/cash-flow/",
            {"start_date": "2026-03-01", "end_date": "2026-03-31"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_revenue_q"], 10000)
        self.assertEqual(data["total_expenses_q"], 5000)
        self.assertEqual(data["net_q"], 5000)
        self.assertEqual(data["period_start"], "2026-03-01")
        self.assertEqual(data["period_end"], "2026-03-31")

    def test_cash_flow_view_missing_dates(self) -> None:
        """Should return 400 when dates are missing."""
        response = self.client.get("/api/accounting/cash-flow/")
        self.assertEqual(response.status_code, 400)

    def test_cash_flow_view_invalid_date(self) -> None:
        """Should return 400 for invalid date format."""
        response = self.client.get(
            "/api/accounting/cash-flow/",
            {"start_date": "invalid", "end_date": "2026-03-31"},
        )
        self.assertEqual(response.status_code, 400)

    def test_accounts_summary_view(self) -> None:
        """GET /api/accounting/accounts/ should return accounts summary."""
        response = self.client.get("/api/accounting/accounts/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_receivable_q"], 10000)
        self.assertEqual(data["total_payable_q"], 5000)
        self.assertIn("receivables", data)
        self.assertIn("payables", data)

    def test_accounts_summary_view_with_as_of(self) -> None:
        """Should accept as_of parameter."""
        response = self.client.get(
            "/api/accounting/accounts/",
            {"as_of": "2026-03-14"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["overdue_receivable_q"], 10000)
        self.assertEqual(data["overdue_payable_q"], 5000)

    def test_entries_view(self) -> None:
        """GET /api/accounting/entries/ should return all entries."""
        response = self.client.get("/api/accounting/entries/")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 2)

    def test_entries_view_filter_by_type(self) -> None:
        """Should filter by type parameter."""
        response = self.client.get(
            "/api/accounting/entries/",
            {"type": "expense"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["type"], "expense")

    def test_entries_view_pagination(self) -> None:
        """Should support limit and offset."""
        response = self.client.get(
            "/api/accounting/entries/",
            {"limit": "1", "offset": "0"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 1)

    def test_create_payable_view(self) -> None:
        """POST /api/accounting/payables/ should create payable."""
        response = self.client.post(
            "/api/accounting/payables/",
            {
                "description": "Nova compra",
                "amount_q": 25000,
                "due_date": "2026-03-25",
                "category": "insumos",
                "supplier_name": "Fornecedor X",
                "reference": "PO-NEW",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIsNotNone(data["entry_id"])

    def test_create_payable_view_validation(self) -> None:
        """Should validate required fields."""
        response = self.client.post(
            "/api/accounting/payables/",
            {"description": "Missing fields"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unauthenticated_access_denied(self) -> None:
        """Should return 401/403 for unauthenticated requests."""
        client = APIClient()  # No authentication
        response = client.get("/api/accounting/cash-flow/")

        self.assertIn(response.status_code, [401, 403])

    def test_backend_not_configured(self) -> None:
        """Should return 503 when backend is not configured."""
        from shopman.accounting.api.views import set_accounting_backend
        set_accounting_backend(None)

        response = self.client.get(
            "/api/accounting/cash-flow/",
            {"start_date": "2026-03-01", "end_date": "2026-03-31"},
        )

        self.assertEqual(response.status_code, 503)
