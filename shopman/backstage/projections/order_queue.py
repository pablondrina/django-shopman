"""OrderQueueProjection — read models for the operator order queue (Fase 4).

Translates the active order queue into immutable projections for the operator
dashboard. Replaces the inline ``_enrich_order`` / ``_status_counts`` logic
from ``shopman.backstage.views.orders``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils import timezone
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.shop.services import payment as payment_svc
from shopman.shop.services.order_helpers import get_fulfillment_type

from shopman.shop.projections.types import (
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    PAYMENT_METHOD_LABELS_PT,
    OrderItemProjection,
    TimelineEventProjection,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────

ACTIVE_STATUSES = ("new", "confirmed", "preparing", "ready", "dispatched", "delivered")

CHANNEL_ICONS: dict[str, str] = {
    "web": "language",
    "whatsapp": "chat",
    "ifood": "fastfood",
    "pos": "storefront",
}
_DEFAULT_CHANNEL_ICON = "shopping_bag"

NEXT_STATUS_MAP: dict[str, str] = {
    "confirmed": "preparing",
    "preparing": "ready",
    "ready": "completed",
    "dispatched": "delivered",
    "delivered": "completed",
}

NEXT_ACTION_LABELS: dict[str, str] = {
    "confirmed": "Iniciar Preparo \u25b8",
    "preparing": "Marcar Pronto \u25b8",
    "ready": "Entregar \u2713",
    "dispatched": "Marcar Entregue \u2713",
    "delivered": "Concluir \u2713",
}

READY_DELIVERY_LABEL = "Saiu para Entrega \u25b8"


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class OrderCardProjection:
    """A single order card in the operator queue."""

    ref: str
    status: str
    status_label: str
    status_color: str
    channel_ref: str
    channel_icon: str
    customer_name: str
    created_at_display: str
    elapsed_seconds: int
    timer_class: str  # "timer-ok", "timer-warning", "timer-urgent", "timer-muted"
    items_summary: str
    items_count: int
    total_display: str
    fulfillment_icon: str  # Material Symbol ligature
    fulfillment_label: str
    can_confirm: bool
    can_advance: bool
    next_status: str
    next_action_label: str
    payment_method: str
    payment_method_label: str
    payment_status: str
    has_notes: bool


@dataclass(frozen=True)
class OperatorOrderProjection:
    """Expanded detail for a single order (operator side-panel)."""

    ref: str
    status: str
    status_label: str
    status_color: str
    customer_name: str
    channel_ref: str
    channel_icon: str
    fulfillment_label: str
    total_display: str
    items: tuple[OrderItemProjection, ...]
    timeline: tuple[TimelineEventProjection, ...]
    internal_notes: str
    payment_method: str
    payment_method_label: str
    payment_status: str


@dataclass(frozen=True)
class OrderQueueProjection:
    """Top-level read model for the operator order queue."""

    orders: tuple[OrderCardProjection, ...]
    counts: dict[str, int]  # status → count, includes "all"
    active_filter: str


# ── Builders ───────────────────────────────────────────────────────────


def build_order_queue(
    *,
    filter_status: str = "all",
) -> OrderQueueProjection:
    """Build the operator order queue projection.

    Queries all active orders, counts per status, then applies filter.
    """
    all_orders = list(
        Order.objects.filter(status__in=ACTIVE_STATUSES)
        .prefetch_related("items")
        .order_by("created_at")
    )

    counts = _status_counts(all_orders)

    if filter_status != "all" and filter_status in ACTIVE_STATUSES:
        filtered = [o for o in all_orders if o.status == filter_status]
    else:
        filtered = all_orders
        filter_status = "all"

    cards = tuple(_build_card(o) for o in filtered)

    return OrderQueueProjection(
        orders=cards,
        counts=counts,
        active_filter=filter_status,
    )


def build_operator_order(order: Order) -> OperatorOrderProjection:
    """Build the expanded detail projection for a single order."""
    items = tuple(
        OrderItemProjection(
            sku=it.sku,
            name=it.name or it.sku,
            qty=int(it.qty),
            unit_price_display=_money(it.unit_price_q),
            total_display=_money(it.line_total_q),
        )
        for it in order.items.all()
    )

    timeline = _build_timeline(order)
    customer_name = (
        order.data.get("customer", {}).get("name", "")
        or order.handle_ref
        or ""
    )
    payment_data = order.data.get("payment", {})
    method = payment_data.get("method", "")

    return OperatorOrderProjection(
        ref=order.ref,
        status=order.status,
        status_label=ORDER_STATUS_LABELS_PT.get(order.status, order.status),
        status_color=ORDER_STATUS_COLORS.get(order.status, "bg-muted text-muted-foreground"),
        customer_name=customer_name,
        channel_ref=order.channel_ref or "",
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        fulfillment_label="Delivery" if _is_delivery(order) else "Retirada",
        total_display=_money(order.total_q),
        items=items,
        timeline=timeline,
        internal_notes=order.data.get("internal_notes", ""),
        payment_method=method,
        payment_method_label=PAYMENT_METHOD_LABELS_PT.get(method, method),
        payment_status=payment_svc.get_payment_status(order) or "",
    )


def build_order_card(order: Order) -> OrderCardProjection:
    """Build a single order card projection (for HTMX partial re-renders)."""
    return _build_card(order)


# ── Internals ──────────────────────────────────────────────────────────


def _build_card(order: Order) -> OrderCardProjection:
    now = timezone.now()
    elapsed = (now - order.created_at).total_seconds()

    timer_class = _timer_class(order.status, elapsed)

    items_qs = list(order.items.all()[:4])
    items_summary = ", ".join(
        f"{int(it.qty)}x {it.name or it.sku}" for it in items_qs[:3]
    )
    if len(items_qs) > 3:
        items_summary += "..."

    items_count = order.items.count()

    is_delivery = _is_delivery(order)
    fulfillment_icon = "local_shipping" if is_delivery else "storefront"
    fulfillment_label = "Delivery" if is_delivery else "Retirada"

    customer_name = (
        order.data.get("customer", {}).get("name", "")
        or order.handle_ref
        or ""
    )

    next_status = _next_status(order)
    next_label = _next_label(order)

    payment_data = order.data.get("payment", {})
    method = payment_data.get("method", "")

    return OrderCardProjection(
        ref=order.ref,
        status=order.status,
        status_label=ORDER_STATUS_LABELS_PT.get(order.status, order.status),
        status_color=ORDER_STATUS_COLORS.get(order.status, "bg-muted text-muted-foreground"),
        channel_ref=order.channel_ref or "",
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        customer_name=customer_name,
        created_at_display=_format_datetime(order.created_at),
        elapsed_seconds=int(elapsed),
        timer_class=timer_class,
        items_summary=items_summary,
        items_count=items_count,
        total_display=_money(order.total_q),
        fulfillment_icon=fulfillment_icon,
        fulfillment_label=fulfillment_label,
        can_confirm=order.status == "new",
        can_advance=order.status in ("confirmed", "preparing", "ready", "dispatched", "delivered"),
        next_status=next_status,
        next_action_label=next_label,
        payment_method=method,
        payment_method_label=PAYMENT_METHOD_LABELS_PT.get(method, method),
        payment_status=payment_svc.get_payment_status(order) or "",
        has_notes=bool(order.data.get("internal_notes")),
    )


def _timer_class(status: str, elapsed: float) -> str:
    if status == "new":
        if elapsed < 180:
            return "timer-ok"
        elif elapsed < 240:
            return "timer-warning"
        else:
            return "timer-urgent"
    return "timer-muted"


def _is_delivery(order: Order) -> bool:
    return get_fulfillment_type(order) == "delivery"


def _next_status(order: Order) -> str:
    if order.status == "ready" and _is_delivery(order):
        return "dispatched"
    return NEXT_STATUS_MAP.get(order.status, "")


def _next_label(order: Order) -> str:
    if order.status == "ready" and _is_delivery(order):
        return READY_DELIVERY_LABEL
    return NEXT_ACTION_LABELS.get(order.status, "")


def _status_counts(orders: list[Order]) -> dict[str, int]:
    counts: dict[str, int] = dict.fromkeys(ACTIVE_STATUSES, 0)
    for order in orders:
        if order.status in counts:
            counts[order.status] += 1
    counts["all"] = sum(counts.values())
    return counts


def _build_timeline(order: Order) -> tuple[TimelineEventProjection, ...]:
    events = order.events.order_by("seq")
    result: list[TimelineEventProjection] = []
    for event in events:
        payload = event.payload or {}
        new_status = payload.get("new_status", "")
        if event.type == "status_changed" and new_status:
            label = ORDER_STATUS_LABELS_PT.get(new_status, new_status)
        else:
            label = event.type.replace("_", " ").title()

        result.append(
            TimelineEventProjection(
                label=label,
                event_type=event.type,
                timestamp_display=_format_datetime(event.created_at),
            )
        )
    return tuple(result)


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


def _format_datetime(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%d/%m às %H:%M")
