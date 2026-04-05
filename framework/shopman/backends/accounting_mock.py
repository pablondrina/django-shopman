"""
Mock Accounting Backend — Para desenvolvimento e testes.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

from shopman.ordering.protocols import (
    AccountEntry,
    AccountsSummary,
    CashFlowSummary,
    CreateEntryResult,
)


class MockAccountingBackend:
    """
    Backend contábil mock para testes e desenvolvimento.

    Armazena lançamentos em memória.
    """

    def __init__(self) -> None:
        self._entries: list[AccountEntry] = []

    def get_cash_flow(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> CashFlowSummary:
        """Calcula fluxo de caixa a partir dos lançamentos em memória."""
        period_entries = [
            e for e in self._entries
            if start_date <= e.date <= end_date
        ]

        revenue = [e for e in period_entries if e.type == "revenue"]
        expenses = [e for e in period_entries if e.type == "expense"]

        total_revenue_q = sum(e.amount_q for e in revenue)
        total_expenses_q = sum(e.amount_q for e in expenses)

        revenue_by_cat: dict[str, int] = {}
        for e in revenue:
            revenue_by_cat[e.category] = revenue_by_cat.get(e.category, 0) + e.amount_q

        expenses_by_cat: dict[str, int] = {}
        for e in expenses:
            expenses_by_cat[e.category] = expenses_by_cat.get(e.category, 0) + e.amount_q

        return CashFlowSummary(
            period_start=start_date,
            period_end=end_date,
            total_revenue_q=total_revenue_q,
            total_expenses_q=total_expenses_q,
            net_q=total_revenue_q - total_expenses_q,
            balance_q=total_revenue_q - total_expenses_q,
            revenue_by_category=revenue_by_cat,
            expenses_by_category=expenses_by_cat,
        )

    def get_accounts_summary(
        self,
        *,
        as_of: date | None = None,
    ) -> AccountsSummary:
        """Retorna contas a pagar e receber pendentes."""
        ref_date = as_of or date.today()

        receivables = [
            e for e in self._entries
            if e.type == "revenue" and e.status == "pending"
        ]
        payables = [
            e for e in self._entries
            if e.type == "expense" and e.status == "pending"
        ]

        total_receivable_q = sum(e.amount_q for e in receivables)
        total_payable_q = sum(e.amount_q for e in payables)
        overdue_receivable_q = sum(
            e.amount_q for e in receivables
            if e.due_date and e.due_date < ref_date
        )
        overdue_payable_q = sum(
            e.amount_q for e in payables
            if e.due_date and e.due_date < ref_date
        )

        return AccountsSummary(
            total_receivable_q=total_receivable_q,
            total_payable_q=total_payable_q,
            overdue_receivable_q=overdue_receivable_q,
            overdue_payable_q=overdue_payable_q,
            receivables=receivables,
            payables=payables,
        )

    def list_entries(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        type: str | None = None,
        status: str | None = None,
        category: str | None = None,
        reference: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[AccountEntry]:
        """Lista lançamentos com filtros."""
        entries = list(self._entries)

        if start_date:
            entries = [e for e in entries if e.date >= start_date]
        if end_date:
            entries = [e for e in entries if e.date <= end_date]
        if type:
            entries = [e for e in entries if e.type == type]
        if status:
            entries = [e for e in entries if e.status == status]
        if category:
            entries = [e for e in entries if e.category == category]
        if reference:
            entries = [e for e in entries if e.reference == reference]

        entries.sort(key=lambda e: e.date, reverse=True)
        return entries[offset:offset + limit]

    def create_payable(
        self,
        *,
        description: str,
        amount_q: int,
        due_date: date,
        category: str,
        supplier_name: str | None = None,
        reference: str | None = None,
        notes: str | None = None,
    ) -> CreateEntryResult:
        """Cria conta a pagar mock."""
        entry_id = f"mock_pay_{uuid4().hex[:8]}"
        entry = AccountEntry(
            entry_id=entry_id,
            description=description,
            amount_q=amount_q,
            type="expense",
            category=category,
            date=due_date,
            due_date=due_date,
            status="pending",
            reference=reference,
            supplier_name=supplier_name,
        )
        self._entries.append(entry)
        return CreateEntryResult(success=True, entry_id=entry_id)

    def create_receivable(
        self,
        *,
        description: str,
        amount_q: int,
        due_date: date,
        category: str,
        customer_name: str | None = None,
        reference: str | None = None,
        notes: str | None = None,
    ) -> CreateEntryResult:
        """Cria conta a receber mock."""
        entry_id = f"mock_rec_{uuid4().hex[:8]}"
        entry = AccountEntry(
            entry_id=entry_id,
            description=description,
            amount_q=amount_q,
            type="revenue",
            category=category,
            date=due_date,
            due_date=due_date,
            status="pending",
            reference=reference,
            customer_name=customer_name,
        )
        self._entries.append(entry)
        return CreateEntryResult(success=True, entry_id=entry_id)

    def mark_as_paid(
        self,
        *,
        entry_id: str,
        paid_date: date | None = None,
        amount_q: int | None = None,
    ) -> CreateEntryResult:
        """Marca lançamento como pago."""
        for entry in self._entries:
            if entry.entry_id == entry_id:
                entry.status = "paid"
                entry.paid_date = paid_date or date.today()
                return CreateEntryResult(success=True, entry_id=entry_id)
        return CreateEntryResult(
            success=False,
            error_message=f"Entry not found: {entry_id}",
        )
