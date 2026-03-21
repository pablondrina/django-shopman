"""
Omniman Core Protocols — Interfaces para backends externos.

Este módulo define os protocols (interfaces) que backends devem implementar.
Os protocols vivem no core para que possam ser usados sem dependências circulares.

Implementações concretas vivem em contrib/:
- contrib/payment/adapters/ - Stripe, Pix, Mock
- contrib/stock/adapters/ - Stockman, etc.
- contrib/fiscal/backends/ - Focus NFC-e, Mock
- contrib/accounting/backends/ - Conta Azul, Mock
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Protocol, runtime_checkable


# =============================================================================
# Payment Protocols
# =============================================================================


@dataclass(frozen=True)
class PaymentIntent:
    """Intenção de pagamento criada."""

    intent_id: str
    status: str  # "pending", "authorized", "requires_action", "captured", "failed"
    amount_q: int
    currency: str
    client_secret: str | None = None  # Para frontend (Stripe Elements, etc)
    expires_at: datetime | None = None
    metadata: dict | None = None


@dataclass(frozen=True)
class CaptureResult:
    """Resultado de captura/autorização."""

    success: bool
    transaction_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class RefundResult:
    """Resultado de reembolso."""

    success: bool
    refund_id: str | None = None
    amount_q: int | None = None
    error_code: str | None = None
    message: str | None = None


@dataclass(frozen=True)
class PaymentStatus:
    """Status atual do pagamento."""

    intent_id: str
    status: str  # "pending", "authorized", "captured", "refunded", "failed", "cancelled"
    amount_q: int
    captured_q: int
    refunded_q: int
    currency: str
    metadata: dict | None = None


@runtime_checkable
class PaymentBackend(Protocol):
    """
    Protocol para backends de pagamento.

    Implementações devem fornecer métodos para:
    - Criar intenções de pagamento
    - Autorizar e capturar pagamentos
    - Processar reembolsos
    - Consultar status

    Implementações disponíveis:
    - omniman.contrib.payment.adapters.mock.MockPaymentBackend
    - omniman.contrib.payment.adapters.stripe.StripePaymentBackend
    - omniman.contrib.payment.adapters.pix.PixPaymentBackend
    """

    def create_intent(
        self,
        amount_q: int,
        currency: str,
        *,
        reference: str | None = None,
        metadata: dict | None = None,
    ) -> PaymentIntent:
        """
        Cria intenção de pagamento.

        Args:
            amount_q: Valor em centavos
            currency: Código ISO 4217 (ex: "BRL")
            reference: Referência externa (session_key ou order_ref)
            metadata: Dados adicionais

        Returns:
            PaymentIntent com ID e status
        """
        ...

    def authorize(
        self,
        intent_id: str,
        *,
        payment_method: str | None = None,
    ) -> CaptureResult:
        """
        Autoriza pagamento (não captura ainda).

        Args:
            intent_id: ID da intenção
            payment_method: Método de pagamento (token, card_id, etc)

        Returns:
            CaptureResult com status da autorização
        """
        ...

    def capture(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reference: str | None = None,
    ) -> CaptureResult:
        """
        Captura pagamento autorizado.

        Args:
            intent_id: ID da intenção
            amount_q: Valor a capturar (None = total)
            reference: Referência do pedido (order_ref)

        Returns:
            CaptureResult com transaction_id
        """
        ...

    def refund(
        self,
        intent_id: str,
        *,
        amount_q: int | None = None,
        reason: str | None = None,
    ) -> RefundResult:
        """
        Processa reembolso.

        Args:
            intent_id: ID da intenção
            amount_q: Valor a reembolsar (None = total)
            reason: Motivo do reembolso

        Returns:
            RefundResult com refund_id
        """
        ...

    def cancel(self, intent_id: str) -> bool:
        """
        Cancela intenção não capturada.

        Returns:
            True se cancelado com sucesso
        """
        ...

    def get_status(self, intent_id: str) -> PaymentStatus:
        """
        Consulta status atual do pagamento.

        Returns:
            PaymentStatus com detalhes
        """
        ...


# =============================================================================
# Fiscal Protocols
# =============================================================================


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
    """
    Protocol para backends fiscais.

    Implementações:
    - FocusNFCeBackend: NFC-e via Focus API
    - MockFiscalBackend: Para testes
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
        """
        Emite documento fiscal.

        Args:
            reference: Referência única (ex: Order.ref "ORD-2026-001")
            items: Lista de itens [{
                description, ncm, cfop, quantity, unit,
                unit_price_q, total_q, tax_info
            }]
            customer: Dados do consumidor (CPF opcional para NFC-e)
                      {cpf?, name?, address?}
            payment: Dados do pagamento {
                method (01=dinheiro, 03=cartao_credito, 04=cartao_debito,
                        05=credito_loja, 15=boleto, 17=pix),
                amount_q
            }
            additional_info: Informações complementares

        Returns:
            FiscalDocumentResult
        """
        ...

    def query_status(
        self,
        *,
        reference: str,
    ) -> FiscalDocumentResult:
        """Consulta status de documento fiscal emitido."""
        ...

    def cancel(
        self,
        *,
        reference: str,
        reason: str,
    ) -> FiscalCancellationResult:
        """
        Cancela documento fiscal.

        Regras SEFAZ:
        - Só pode cancelar dentro de 30 minutos da autorização.
        - Motivo obrigatório (min 15 caracteres).
        """
        ...


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

    Implementações:
    - ContaAzulBackend: Conta Azul API
    - MockAccountingBackend: Para testes

    Responsabilidades:
    - Consulta de receitas e despesas
    - Criação de contas a pagar (compras → Étienne)
    - Fluxo de caixa (Anaïs)
    - Contas a pagar/receber (Anaïs)
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
