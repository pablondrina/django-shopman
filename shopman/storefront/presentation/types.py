"""Storefront-only presentation types.

These display view-models are consumed solely by the storefront surface, so they
live here rather than polluting the shared ``shop/projections/types.py`` kernel.
Cross-surface data shapes (``OrderItemProjection``, ``TimelineEventProjection``,
``Availability``, ``Action`` …) stay in ``shop.projections.types``.
"""

from __future__ import annotations

from dataclasses import dataclass


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
class PaymentMethodOptionProjection:
    """A payment method available on the channel."""

    ref: str    # "pix", "card", "cash", "external"
    label: str  # pt-BR label
    is_default: bool


@dataclass(frozen=True)
class OrderProgressStepProjection:
    """A customer-facing step in the canonical order progress path."""

    label: str
    key: str
    state: str  # completed | current | pending | cancelled
    timestamp_display: str | None = None


@dataclass(frozen=True)
class FulfillmentProjection:
    """A fulfillment record (delivery or pickup)."""

    status: str
    status_label: str
    tracking_label: str
    tracking_code: str | None
    tracking_url: str | None
    carrier: str | None
    dispatched_at_display: str | None
    delivered_at_display: str | None


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
