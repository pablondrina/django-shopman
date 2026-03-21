"""
Production Backend Protocol.

Defines the interface for Stockman to interact with production systems
(e.g., Craftsman) for requesting production when demand exceeds supply.

Vocabulary mapping (Stockman → Craftsman):
    request_production()  →  craft.plan() + craft.schedule()
    check_status()        →  WorkOrder.status
    cancel_request()      →  WorkOrder.cancel()
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any, Protocol, runtime_checkable


# ══════════════════════════════════════════════════════════════
# ENUMS
# ══════════════════════════════════════════════════════════════


class ProductionPriority(str, Enum):
    """Prioridade de produção."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ProductionStatusEnum(str, Enum):
    """Status de um pedido de produção."""

    REQUESTED = "requested"  # Solicitação criada
    PLANNED = "planned"  # Plan aprovado
    SCHEDULED = "scheduled"  # WorkOrder criada
    IN_PROGRESS = "in_progress"  # Produção em andamento
    COMPLETED = "completed"  # Produção concluída
    CANCELLED = "cancelled"  # Cancelado
    FAILED = "failed"  # Falhou (sem materiais, etc.)


# ══════════════════════════════════════════════════════════════
# DATA TYPES
# ══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class ProductionRequest:
    """Solicitação de produção."""

    sku: str
    quantity: Decimal
    target_date: date
    priority: ProductionPriority = ProductionPriority.NORMAL
    reference: str | None = None  # Hold ID que originou a demanda
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductionStatus:
    """Status atual de uma solicitação de produção."""

    request_id: str  # ID do pedido de produção
    sku: str
    quantity: Decimal
    status: ProductionStatusEnum
    target_date: date
    estimated_completion: date | None = None
    work_order_id: str | None = None  # UUID da WorkOrder (se criada)
    message: str | None = None


@dataclass(frozen=True)
class ProductionResult:
    """Resultado de uma solicitação de produção."""

    success: bool
    request_id: str | None = None  # Formato: "production:{pk}"
    status: ProductionStatusEnum | None = None
    message: str | None = None
    work_order_id: str | None = None


# ══════════════════════════════════════════════════════════════
# PROTOCOL
# ══════════════════════════════════════════════════════════════


@runtime_checkable
class ProductionBackend(Protocol):
    """
    Interface para Stockman solicitar produção.

    Este protocol permite que o Stockman dispare produção quando:
    - availability_policy é "planned_ok" ou "demand_ok"
    - Um Hold é criado para demanda futura
    - A demanda excede o planejado

    Implementações:
        - CraftsmanBackend: Usa craft.plan() + craft.schedule()
        - MockProductionBackend: Para testes sem produção real
    """

    def request_production(
        self,
        request: ProductionRequest,
    ) -> ProductionResult:
        """
        Solicita produção de um produto.

        Fluxo típico no Craftsman:
        1. Encontra Recipe para o SKU
        2. Cria Plan com craft.plan()
        3. Aprova e agenda com craft.schedule()

        Args:
            request: Dados da solicitação

        Returns:
            Resultado com ID do pedido ou erro
        """
        ...

    def check_status(
        self,
        request_id: str,
    ) -> ProductionStatus | None:
        """
        Verifica status de uma solicitação.

        Args:
            request_id: ID do pedido de produção

        Returns:
            Status atual ou None se não encontrado
        """
        ...

    def cancel_request(
        self,
        request_id: str,
        reason: str = "cancelled",
    ) -> ProductionResult:
        """
        Cancela uma solicitação de produção.

        Args:
            request_id: ID do pedido
            reason: Motivo do cancelamento

        Returns:
            Resultado do cancelamento
        """
        ...

    def list_pending(
        self,
        sku: str | None = None,
        target_date: date | None = None,
    ) -> list[ProductionStatus]:
        """
        Lista solicitações pendentes.

        Args:
            sku: Filtrar por SKU (opcional)
            target_date: Filtrar por data (opcional)

        Returns:
            Lista de status das solicitações
        """
        ...
