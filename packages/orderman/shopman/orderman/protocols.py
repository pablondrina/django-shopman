"""
Orderman Core Protocols — Interfaces para backends externos.

Este módulo define os protocols (interfaces) que backends devem implementar.
Os protocols vivem no core para que possam ser usados sem dependências circulares.

Implementações concretas vivem em contrib/:
- contrib/payment/adapters/ - Stripe, Pix, Mock
- contrib/stock/adapters/ - Stockman, etc.
- contrib/fiscal/backends/ - Focus NFe, Mock
- contrib/accounting/backends/ - Conta Azul, Mock
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol, runtime_checkable

# Payment Protocols vivem em shopman.payman.protocols — importar de lá diretamente.
# orderman não re-exporta payman para manter standalone instalável.

# =============================================================================
# Fiscal Protocols
# =============================================================================
# O contrato fiscal (FiscalBackend Protocol + FiscalDocumentResult +
# FiscalCancellationResult) vive na persona Fiscalman desde 2026-06-29:
#   from shopman.fiscalman.contracts import FiscalBackend, FiscalDocumentResult, ...
# Estava estacionado aqui sem uso interno do orderman.


# =============================================================================
# Accounting Protocols
# =============================================================================


@dataclass
class AccountEntry:
    """Lançamento financeiro (receita ou despesa)."""

    entry_id: str
    description: str
    amount_q: int
    type: str  # "revenue" ou "expense"
    category: str
    date: date
    due_date: date | None = None
    paid_date: date | None = None
    status: str = "pending"  # pending, paid, overdue, cancelled
    reference: str | None = None
    customer_name: str | None = None
    supplier_name: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class CashFlowSummary:
    """Resumo de fluxo de caixa para período."""

    period_start: date
    period_end: date
    total_revenue_q: int
    total_expenses_q: int
    net_q: int
    balance_q: int
    revenue_by_category: dict[str, int] = field(default_factory=dict)
    expenses_by_category: dict[str, int] = field(default_factory=dict)


@dataclass
class AccountsSummary:
    """Resumo de contas a pagar/receber."""

    total_receivable_q: int
    total_payable_q: int
    overdue_receivable_q: int
    overdue_payable_q: int
    receivables: list[AccountEntry] = field(default_factory=list)
    payables: list[AccountEntry] = field(default_factory=list)


@dataclass
class CreateEntryResult:
    """Resultado da criação de lançamento."""

    success: bool
    entry_id: str | None = None
    error_message: str | None = None


@runtime_checkable
class AccountingBackend(Protocol):
    """
    Protocol para backends contábeis/financeiros.

    Extension point intencional — não há implementação padrão.
    O sistema funciona sem backend contábil; ative em produção via adapter
    configurado no settings da instância.

    Implementações de referência:
    - ContaAzulBackend: Conta Azul API
    - MockAccountingBackend: Para testes unitários

    Responsabilidades:
    - Consulta de receitas e despesas
    - Criação de contas a pagar
    - Fluxo de caixa
    - Contas a pagar/receber
    """

    def get_cash_flow(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> CashFlowSummary:
        """Retorna resumo de fluxo de caixa do período."""
        ...

    def get_accounts_summary(
        self,
        *,
        as_of: date | None = None,
    ) -> AccountsSummary:
        """Retorna resumo de contas a pagar/receber."""
        ...

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
        ...

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
        """Cria conta a pagar."""
        ...

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
        """Cria conta a receber."""
        ...

    def mark_as_paid(
        self,
        *,
        entry_id: str,
        paid_date: date | None = None,
        amount_q: int | None = None,
    ) -> CreateEntryResult:
        """Marca lançamento como pago."""
        ...
