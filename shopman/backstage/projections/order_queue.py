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

from shopman.shop.projections.types import (
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    PAYMENT_METHOD_LABELS_PT,
    OrderItemProjection,
    TimelineEventProjection,
)
from shopman.shop.services import payment as payment_svc
from shopman.shop.services.order_helpers import get_fulfillment_type

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────────

ACTIVE_STATUSES = ("new", "confirmed", "preparing", "ready", "dispatched", "delivered")

_PAYMENT_COMPLETE = frozenset({"captured", "paid"})
_OFFLINE_METHODS = frozenset({"cash", "credit", "debit", "external", ""})

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
    "confirmed": "Iniciar preparo",
    "preparing": "Marcar pronto",
    "ready": "Marcar como Retirado",
    "dispatched": "Marcar como Entregue",
    "delivered": "Concluir",
}

READY_DELIVERY_LABEL = "Saiu para entrega"


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
    payment_pending: bool
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


@dataclass(frozen=True)
class TwoZoneQueueProjection:
    """Operator queue grouped by action area: Entrada, Preparo and Saída."""

    entrada: tuple[OrderCardProjection, ...]
    preparing_count: int
    preparo: tuple[OrderCardProjection, ...]
    saida_retirada: tuple[OrderCardProjection, ...]
    saida_delivery: tuple[OrderCardProjection, ...]
    saida_delivery_transit: tuple[OrderCardProjection, ...]
    saida_delivery_count: int
    saida_count: int
    total_count: int


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
    customer_data = order.data.get("customer", {})
    customer_name = _format_customer_display(
        customer_data.get("name", "")
        or customer_data.get("phone", "")
        or order.data.get("customer_phone", "")
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


def build_two_zone_queue() -> TwoZoneQueueProjection:
    """Build the operator queue grouped by the next physical action."""
    all_orders = list(
        Order.objects.filter(status__in=ACTIVE_STATUSES)
        .prefetch_related("items")
        .order_by("created_at")
    )

    entrada = tuple(_build_card(o) for o in all_orders if o.status == "new")
    preparo = tuple(_build_card(o) for o in all_orders if o.status in ("confirmed", "preparing"))
    preparing_count = len(preparo)

    ready_orders = [o for o in all_orders if o.status == "ready"]
    saida_retirada = tuple(_build_card(o) for o in ready_orders if not _is_delivery(o))
    saida_delivery = tuple(_build_card(o) for o in ready_orders if _is_delivery(o))
    saida_delivery_transit = tuple(
        _build_card(o) for o in all_orders if o.status in ("dispatched", "delivered")
    )

    return TwoZoneQueueProjection(
        entrada=entrada,
        preparing_count=preparing_count,
        preparo=preparo,
        saida_retirada=saida_retirada,
        saida_delivery=saida_delivery,
        saida_delivery_transit=saida_delivery_transit,
        saida_delivery_count=len(saida_delivery) + len(saida_delivery_transit),
        saida_count=len(saida_retirada) + len(saida_delivery) + len(saida_delivery_transit),
        total_count=len(all_orders),
    )


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

    customer_data = order.data.get("customer", {})
    customer_name = _format_customer_display(
        customer_data.get("name", "")
        or customer_data.get("phone", "")
        or order.data.get("customer_phone", "")
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
        can_advance=bool(next_status),
        next_status=next_status,
        next_action_label=next_label,
        payment_method=method,
        payment_method_label=PAYMENT_METHOD_LABELS_PT.get(method, method),
        payment_status=payment_svc.get_payment_status(order) or "",
        payment_pending=_is_payment_pending(order, method, payment_svc.get_payment_status(order) or ""),
        has_notes=bool(order.data.get("internal_notes")),
    )


def _is_payment_pending(order: Order, method: str, payment_status: str) -> bool:
    """True when the order needs payment capture before it can be confirmed."""
    if order.status != "new":
        return False
    if method in _OFFLINE_METHODS:
        return False
    return payment_status not in _PAYMENT_COMPLETE


def _format_customer_display(value: str) -> str:
    label = (value or "").strip()
    if not label:
        return ""

    digits = "".join(ch for ch in label if ch.isdigit())
    if not digits:
        return label

    looks_like_phone = label.startswith("+") or label.startswith("(") or len(digits) >= 10
    if not looks_like_phone:
        return label

    if digits.startswith("0") and len(digits) in (11, 12):
        digits = digits[1:]

    if digits.startswith("55") and len(digits) in (12, 13):
        ddd = digits[2:4]
        number = digits[4:]
        if len(number) == 9:
            return f"+55 {ddd} {number[:5]}-{number[5:]}"
        if len(number) == 8:
            return f"+55 {ddd} {number[:4]}-{number[4:]}"

    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"

    if label.startswith("+"):
        return "+" + digits
    return label


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
