"""
Inventory Protocol — interface for Craftsman to interact with stock systems.

Defines how Craftsman communicates with inventory (e.g., Stockman) for
material reservation, consumption, release, and production receipt.

Vocabulary mapping (Craftsman → Stockman):
    reserve()   →  stock.hold()
    consume()   →  stock.fulfill()
    release()   →  stock.release()
    receive()   →  stock.receive()
    available() →  stock.available()
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


# ══════════════════════════════════════════════════════════════
# DATA TYPES
# ══════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class MaterialNeed:
    """Material necessário para produção."""

    sku: str
    quantity: Decimal
    unit: str = "kg"
    position_ref: str | None = None


@dataclass(frozen=True)
class MaterialUsed:
    """Material efetivamente consumido."""

    sku: str
    quantity: Decimal


@dataclass(frozen=True)
class MaterialProduced:
    """Produto de saída da produção."""

    sku: str
    quantity: Decimal
    position_ref: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class MaterialStatus:
    """Status de disponibilidade de um material."""

    sku: str
    needed: Decimal
    available: Decimal

    @property
    def sufficient(self) -> bool:
        return self.available >= self.needed

    @property
    def shortage(self) -> Decimal:
        return max(Decimal("0"), self.needed - self.available)


@dataclass(frozen=True)
class AvailabilityResult:
    """Resultado de verificação de disponibilidade."""

    all_available: bool
    materials: list[MaterialStatus] = field(default_factory=list)


@dataclass(frozen=True)
class MaterialHold:
    """Reserva de material."""

    sku: str
    quantity: Decimal
    hold_id: str  # Formato: "hold:{pk}" (convenção Stockman)


@dataclass(frozen=True)
class ReserveResult:
    """Resultado de reserva de materiais."""

    success: bool
    holds: list[MaterialHold] = field(default_factory=list)
    failed: list[MaterialStatus] = field(default_factory=list)
    message: str | None = None


@dataclass(frozen=True)
class MaterialAdjustment:
    """Ajuste entre reservado e consumido."""

    sku: str
    reserved: Decimal
    consumed: Decimal

    @property
    def delta(self) -> Decimal:
        """Positivo = usou mais, negativo = sobrou."""
        return self.consumed - self.reserved


@dataclass(frozen=True)
class ConsumeResult:
    """Resultado de consumo de materiais."""

    success: bool
    consumed: list[MaterialUsed] = field(default_factory=list)
    adjustments: list[MaterialAdjustment] = field(default_factory=list)
    message: str | None = None


@dataclass(frozen=True)
class ReleaseResult:
    """Resultado de liberação de materiais."""

    success: bool
    released: list[MaterialHold] = field(default_factory=list)
    message: str | None = None


@dataclass(frozen=True)
class ReceiveResult:
    """Resultado de recebimento de produção."""

    success: bool
    quant_id: str | None = None  # Formato: "quant:{pk}"
    message: str | None = None


# ══════════════════════════════════════════════════════════════
# PROTOCOL
# ══════════════════════════════════════════════════════════════


@runtime_checkable
class InventoryProtocol(Protocol):
    """
    Interface para Craftsman acessar estoque de materiais.

    Se não configurado: Craftsman funciona standalone (puro registro).
    Se configurado: finish chama consume + receive. void chama release.

    Implementações:
        - StockingBackend (contrib): Usa a API do Stockman
        - NoopInventory (adapters): Para testes sem estoque real
    """

    def available(self, materials: list[MaterialNeed]) -> AvailabilityResult:
        """Verifica disponibilidade de materiais."""
        ...

    def reserve(
        self,
        materials: list[MaterialNeed],
        ref: str,
        metadata: dict[str, Any] | None = None,
    ) -> ReserveResult:
        """Reserva materiais para uma ordem de produção."""
        ...

    def consume(
        self,
        items: list[MaterialUsed],
        ref: str,
    ) -> ConsumeResult:
        """Consome materiais (baixa definitiva)."""
        ...

    def release(
        self,
        ref: str,
        reason: str = "voided",
    ) -> ReleaseResult:
        """Libera materiais reservados (produção cancelada)."""
        ...

    def receive(
        self,
        items: list[MaterialProduced],
        ref: str,
    ) -> ReceiveResult:
        """Registra output de produção no estoque."""
        ...
