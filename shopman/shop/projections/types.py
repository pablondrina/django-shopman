"""Shared projection types."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


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
    Availability.PLANNED_OK: "Lista de espera",
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
    "cash": "Dinheiro",
    "mixed": "Pagamento misto",

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
class Action:
    """Canonical action offered by a Shopman projection to any surface."""

    ref: str
    kind: str
    label: str
    priority: str = "secondary"
    enabled: bool = True
    reason: str = ""
    href: str = ""
    method: str = ""
    payload_schema: dict[str, Any] = field(default_factory=dict)
    idempotency: str = "none"
    confirmation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SavedAddressProjection:
    """A customer's saved delivery address.

    Extended with structured components (route, street_number, lat/lng,
    place_id, etc.) so the address picker can re-hydrate the form on
    selection without needing a second fetch.
    """

    id: int
    formatted_address: str
    complement: str
    label: str
    is_default: bool
    label_key: str = "home"
    label_custom: str = ""
    # Extended fields — default empty so callers that only need display keep
    # working without extra arguments. All values are strings so they
    # serialise cleanly to JSON for Alpine.
    route: str = ""
    street_number: str = ""
    neighborhood: str = ""
    city: str = ""
    state_code: str = ""
    postal_code: str = ""
    latitude: float | None = None
    longitude: float | None = None
    place_id: str = ""
    delivery_instructions: str = ""


@dataclass(frozen=True)
class AddressAutocompleteProjection:
    """Client-side address autocomplete capability for headless surfaces.

    ``public_api_key`` is intentionally the browser key. It must be restricted
    in Google Cloud; reverse geocoding stays server-side via the advertised
    action ref.
    """

    enabled: bool
    provider: str = "google_places"
    public_api_key: str = ""
    language: str = "pt-BR"
    region: str = "BR"
    countries: tuple[str, ...] = ("br",)
    types: tuple[str, ...] = ("address",)
    fields: tuple[str, ...] = ("formatted_address", "address_components", "geometry", "place_id")
    structured_fields: tuple[str, ...] = (
        "formatted_address",
        "route",
        "street_number",
        "neighborhood",
        "city",
        "state_code",
        "postal_code",
        "country",
        "country_code",
        "latitude",
        "longitude",
        "place_id",
        "complement",
        "delivery_instructions",
        "reference",
        "is_verified",
    )
    reverse_geocode_action_ref: str = "reverse_geocode"
    shop_latitude: float | None = None
    shop_longitude: float | None = None
    bias_radius_m: int = 15000


@dataclass(frozen=True)
class PickupSlotProjection:
    """A single configured pickup time slot."""

    ref: str
    label: str    # e.g. "A partir das 09h"
    starts_at: str  # "09:00"
    enabled: bool = True
    reason: str = ""
    is_earliest: bool = False


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
    actor: str = ""
    detail: str = ""


