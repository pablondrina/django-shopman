"""
Shopman Stock Protocols — Interfaces para backends de estoque.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AvailabilityResult:
    """Resultado de verificação de disponibilidade."""

    available: bool
    available_qty: Decimal
    message: str | None = None


@dataclass(frozen=True)
class HoldResult:
    """Resultado de criação de reserva."""

    success: bool
    hold_id: str | None = None
    error_code: str | None = None
    message: str | None = None
    expires_at: datetime | None = None
    is_planned: bool = False


@dataclass(frozen=True)
class Alternative:
    """Produto alternativo sugerido."""

    sku: str
    name: str
    available_qty: Decimal


@runtime_checkable
class StockBackend(Protocol):
    """
    Protocol para backends de estoque.

    Implementações devem fornecer métodos para:
    - Verificar disponibilidade
    - Criar/liberar/confirmar reservas
    - Sugerir alternativas (opcional)
    """

    def check_availability(
        self,
        sku: str,
        quantity: Decimal,
        target_date: date | None = None,
    ) -> AvailabilityResult:
        ...

    def create_hold(
        self,
        sku: str,
        quantity: Decimal,
        expires_at: datetime | None = None,
        reference: str | None = None,
        target_date: date | None = None,
    ) -> HoldResult:
        ...

    def release_hold(self, hold_id: str) -> None:
        ...

    def fulfill_hold(self, hold_id: str, reference: str | None = None) -> None:
        ...

    def get_alternatives(self, sku: str, quantity: Decimal) -> list[Alternative]:
        ...

    def release_holds_for_reference(self, reference: str) -> int:
        ...

    def receive_return(
        self,
        sku: str,
        quantity: Decimal,
        *,
        reference: str | None = None,
        reason: str = "Devolução",
    ) -> None:
        ...
