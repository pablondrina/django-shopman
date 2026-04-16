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


# ──────────────────────────────────────────────────────────────────────
# Fase 2 — Checkout, Payment, Tracking
# ──────────────────────────────────────────────────────────────────────

PAYMENT_METHOD_LABELS_PT: dict[str, str] = {
    "pix": "PIX",
    "card": "Cartão",
    "cash": "Dinheiro / Maquininha",
    "counter": "Pagar no balcão",
    "external": "Pago online",
}

ORDER_STATUS_LABELS_PT: dict[str, str] = {
    "new": "Recebido",
    "confirmed": "Confirmado",
    "preparing": "Em Preparo",
    "ready": "Pronto",
    "dispatched": "Saiu para entrega",
    "delivered": "Entregue",
    "completed": "Concluído",
    "cancelled": "Cancelado",
    "returned": "Devolvido",
}

ORDER_STATUS_COLORS: dict[str, str] = {
    "new": "bg-info/10 text-info border border-info/20",
    "confirmed": "bg-info/10 text-info border border-info/20",
    "preparing": "bg-warning/10 text-warning border border-warning/20",
    "ready": "bg-success/10 text-success border border-success/20",
    "dispatched": "bg-info/10 text-info border border-info/20",
    "delivered": "bg-success/10 text-success border border-success/20",
    "completed": "bg-success/10 text-success border border-success/20",
    "cancelled": "bg-danger/10 text-danger border border-danger/20",
    "returned": "bg-surface-alt text-on-surface/60 border border-outline",
}


@dataclass(frozen=True)
class SavedAddressProjection:
    """A customer's saved delivery address."""

    id: int
    formatted_address: str
    complement: str
    label: str
    is_default: bool


@dataclass(frozen=True)
class PickupSlotProjection:
    """A single configured pickup time slot."""

    ref: str
    label: str    # e.g. "A partir das 09h"
    starts_at: str  # "09:00"


@dataclass(frozen=True)
class PaymentMethodOptionProjection:
    """A payment method available on the channel."""

    ref: str    # "pix", "card", "cash", "counter"
    label: str  # pt-BR label
    is_default: bool


@dataclass(frozen=True)
class OrderItemProjection:
    """One line item as displayed on order tracking or confirmation."""

    sku: str
    name: str
    qty: int
    unit_price_display: str
    total_display: str


@dataclass(frozen=True)
class TimelineEventProjection:
    """A single event in the order timeline."""

    label: str
    event_type: str
    timestamp_display: str  # pre-formatted local datetime, e.g. "15/04 às 14:32"


@dataclass(frozen=True)
class FulfillmentProjection:
    """A fulfillment record (delivery or pickup)."""

    status: str
    status_label: str
    tracking_code: str | None
    tracking_url: str | None
    carrier: str | None
    dispatched_at_display: str | None
    delivered_at_display: str | None


# ──────────────────────────────────────────────────────────────────────
# Fase 3 — Account, Order History
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OrderSummaryProjection:
    """Compact order summary for account history and order-history pages."""

    ref: str
    created_at_display: str  # "15/04/2026 às 14:32"
    total_q: int
    total_display: str       # "R$ 48,00"
    status: str
    status_label: str
    status_color: str        # Penguin UI token classes
    item_count: int


@dataclass(frozen=True)
class NotificationPrefProjection:
    """A single notification consent channel preference."""

    key: str          # "whatsapp", "email", "sms", "push"
    label: str        # "WhatsApp"
    description: str  # "Receber atualizações via WhatsApp"
    enabled: bool


@dataclass(frozen=True)
class FoodPrefProjection:
    """A single food restriction / dietary preference."""

    key: str       # "sem_gluten"
    label: str     # "Sem Glúten"
    is_active: bool
