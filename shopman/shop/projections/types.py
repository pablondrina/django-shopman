"""Shared projection types."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Availability(StrEnum):
    """Canonical availability states exposed to the storefront UI.

    - AVAILABLE  : plenty of physical stock (or demand_ok policy, no reservation needed)
    - LOW_STOCK  : physical stock is running out — show urgency
    - PLANNED_OK : no physical stock yet, but planned production covers the order
    - UNAVAILABLE: cannot be sold right now (paused, out of stock with no plan)
    """

    AVAILABLE = "available"
    LOW_STOCK = "low_stock"
    PLANNED_OK = "planned_ok"
    UNAVAILABLE = "unavailable"


AVAILABILITY_LABELS_PT: dict[Availability, str] = {
    Availability.AVAILABLE: "Disponível",
    Availability.LOW_STOCK: "Últimas unidades",
    Availability.PLANNED_OK: "Sob encomenda",
    Availability.UNAVAILABLE: "Indisponível",
}


@dataclass(frozen=True)
class CategoryProjection:
    """A catalog category (collection) as exposed to the UI."""

    ref: str
    name: str
    icon: str  # Material Symbols ligature (fallback: "restaurant_menu")
    url: str


@dataclass(frozen=True)
class ComponentProjection:
    """One line of a bundle's composition, as rendered under the PDP.

    ``qty_display`` is a pre-formatted label like ``"2x"`` — templates
    never format numbers themselves.
    """

    sku: str
    name: str
    qty_display: str


@dataclass(frozen=True)
class HappyHourProjection:
    """Happy hour banner state."""

    active: bool
    discount_percent: int
    start: str  # "16:00"
    end: str  # "18:00"
