"""
Inventory Protocol — read-only seam for Craftsman to validate material stock.

Craftsman uses this to *check* ingredient availability (e.g. before increasing a
planned WorkOrder). It is read-only: stock ledger writes (consuming ingredients,
receiving finished goods) are NOT done through this protocol — they flow through
the `production_changed` signal handlers in craftsman.contrib.stockman, the
single canonical craftsman→stockman write path.

If no backend is configured, Craftsman runs standalone and availability checks
are skipped. A backend implementation is provided by Buyman/Material (see
docs/plans/BUYMAN-PROCUREMENT-PLAN.md).

Vocabulary mapping (Craftsman → Stockman):
    available() →  stock.available()
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol, runtime_checkable

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


# ══════════════════════════════════════════════════════════════
# PROTOCOL
# ══════════════════════════════════════════════════════════════


@runtime_checkable
class InventoryProtocol(Protocol):
    """
    Interface read-only para Craftsman validar disponibilidade de insumos.

    Se não configurado: Craftsman funciona standalone (checagem pulada).
    Escrita no ledger de estoque é feita pelo signal-path (contrib.stockman),
    não por este protocolo.
    """

    def available(self, materials: list[MaterialNeed]) -> AvailabilityResult:
        """Verifica disponibilidade de materiais."""
        ...
