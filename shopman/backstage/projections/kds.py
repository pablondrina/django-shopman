"""KDSBoardProjection — read models for the Kitchen Display System (Fase 4).

Translates KDS instances, tickets, and expedition orders into immutable
projections. Replaces the inline ``_enrich_ticket`` / ``_enrich_expedition_order``
logic from ``shopman.backstage.views.kds``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.shop.services.order_helpers import get_fulfillment_type

from .order_queue import _DEFAULT_CHANNEL_ICON, CHANNEL_ICONS

logger = logging.getLogger(__name__)


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class KDSItemProjection:
    """A single item within a KDS ticket."""

    sku: str
    name: str
    qty: int
    notes: str
    checked: bool
    stock_warning: str  # "" = no warning


@dataclass(frozen=True)
class KDSTicketProjection:
    """A KDS ticket card (prep/picking station)."""

    pk: int
    order_ref: str
    channel_icon: str
    customer_name: str
    fulfillment_icon: str
    created_at_display: str
    elapsed_seconds: int
    timer_class: str  # "timer-ok", "timer-warning", "timer-late"
    items: tuple[KDSItemProjection, ...]
    status: str
    all_checked: bool


@dataclass(frozen=True)
class KDSExpeditionCardProjection:
    """An order card in the expedition (dispatch) board."""

    pk: int
    ref: str
    channel_icon: str
    customer_name: str
    fulfillment_icon: str
    fulfillment_label: str
    is_delivery: bool
    items_count: int
    total_display: str


@dataclass(frozen=True)
class KDSInstanceSummaryProjection:
    """A KDS instance in the index (station selector)."""

    ref: str
    name: str
    type: str
    type_display: str
    pending_count: int


@dataclass(frozen=True)
class KDSBoardProjection:
    """Top-level read model for a KDS display."""

    instance_ref: str
    instance_name: str
    instance_type: str
    is_expedition: bool
    tickets: tuple[KDSTicketProjection | KDSExpeditionCardProjection, ...]
    counts: dict[str, int]  # "pending", "in_progress", "total"


# ── Builders ───────────────────────────────────────────────────────────


def build_kds_index() -> tuple[KDSInstanceSummaryProjection, ...]:
    """Build the KDS instance selector (index page)."""
    from shopman.backstage.models import KDSInstance, KDSTicket

    instances = KDSInstance.objects.filter(is_active=True).order_by("name")
    result: list[KDSInstanceSummaryProjection] = []

    for inst in instances:
        if inst.type == "expedition":
            count = Order.objects.filter(status="ready").count()
        else:
            count = KDSTicket.objects.filter(
                kds_instance=inst,
                status__in=["pending", "in_progress"],
            ).count()

        result.append(
            KDSInstanceSummaryProjection(
                ref=inst.ref,
                name=inst.name,
                type=inst.type,
                type_display=inst.get_type_display(),
                pending_count=count,
            )
        )

    return tuple(result)


def build_kds_board(instance_ref: str) -> KDSBoardProjection:
    """Build the KDS board projection for a specific instance."""
    from shopman.backstage.models import KDSInstance, KDSTicket

    instance = KDSInstance.objects.get(ref=instance_ref, is_active=True)

    if instance.type == "expedition":
        return _build_expedition_board(instance)

    tickets_qs = (
        KDSTicket.objects.filter(
            kds_instance=instance,
            status__in=["pending", "in_progress"],
        )
        .select_related("order")
        .order_by("created_at")
    )

    tickets = tuple(_build_ticket(t, instance) for t in tickets_qs)
    pending = sum(1 for t in tickets if t.status == "pending")
    in_progress = sum(1 for t in tickets if t.status == "in_progress")

    return KDSBoardProjection(
        instance_ref=instance.ref,
        instance_name=instance.name,
        instance_type=instance.type,
        is_expedition=False,
        tickets=tickets,
        counts={"pending": pending, "in_progress": in_progress, "total": len(tickets)},
    )


def build_kds_ticket(ticket_pk: int) -> KDSTicketProjection:
    """Build a single ticket projection (for HTMX partial re-renders)."""
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.select_related("order", "kds_instance").get(pk=ticket_pk)
    return _build_ticket(ticket, ticket.kds_instance)


# ── Internals ──────────────────────────────────────────────────────────


def _build_expedition_board(instance) -> KDSBoardProjection:
    orders = Order.objects.filter(status="ready").order_by("created_at")
    cards = tuple(_build_expedition_card(o) for o in orders)

    return KDSBoardProjection(
        instance_ref=instance.ref,
        instance_name=instance.name,
        instance_type=instance.type,
        is_expedition=True,
        tickets=cards,
        counts={"pending": len(cards), "in_progress": 0, "total": len(cards)},
    )


def _build_ticket(ticket, instance) -> KDSTicketProjection:
    now = timezone.now()
    elapsed = (now - ticket.created_at).total_seconds()
    target_sec = instance.target_time_minutes * 60

    if elapsed < target_sec:
        timer_class = "timer-ok"
    elif elapsed < target_sec * 2:
        timer_class = "timer-warning"
    else:
        timer_class = "timer-late"

    order = ticket.order
    customer_name = (
        order.data.get("customer", {}).get("name", "")
        or order.handle_ref
        or ""
    )
    fulfillment_type = get_fulfillment_type(order)
    fulfillment_icon = "local_shipping" if fulfillment_type == "delivery" else "storefront"

    raw_items = ticket.items
    if instance.type == "picking":
        raw_items = _add_stock_warnings(raw_items)

    items = tuple(
        KDSItemProjection(
            sku=it.get("sku", ""),
            name=it.get("name", it.get("sku", "")),
            qty=int(it.get("qty", 1)),
            notes=it.get("notes", ""),
            checked=bool(it.get("checked", False)),
            stock_warning=it.get("stock_warning", ""),
        )
        for it in raw_items
    )

    return KDSTicketProjection(
        pk=ticket.pk,
        order_ref=order.ref,
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        customer_name=customer_name,
        fulfillment_icon=fulfillment_icon,
        created_at_display=_format_datetime(ticket.created_at),
        elapsed_seconds=int(elapsed),
        timer_class=timer_class,
        items=items,
        status=ticket.status,
        all_checked=all(it.checked for it in items) if items else False,
    )


def _build_expedition_card(order: Order) -> KDSExpeditionCardProjection:
    customer_name = (
        order.data.get("customer", {}).get("name", "")
        or order.handle_ref
        or ""
    )
    is_delivery = get_fulfillment_type(order) == "delivery"

    return KDSExpeditionCardProjection(
        pk=order.pk,
        ref=order.ref,
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        customer_name=customer_name,
        fulfillment_icon="local_shipping" if is_delivery else "storefront",
        fulfillment_label="Delivery" if is_delivery else "Retirada",
        is_delivery=is_delivery,
        items_count=order.items.count(),
        total_display=_money(order.total_q),
    )


def _add_stock_warnings(items: list[dict]) -> list[dict]:
    """Add stock_warning to items where physical stock is low or zero."""
    try:
        from shopman.stockman.models import Quant, StockAlert
    except ImportError:
        return items

    skus = [item.get("sku") for item in items if item.get("sku")]
    if not skus:
        return items

    quant_qs = (
        Quant.objects.filter(sku__in=skus)
        .filter(Q(target_date__isnull=True) | Q(target_date__lte=timezone.now().date()))
        .values("sku")
        .annotate(total=Coalesce(Sum("_quantity"), Decimal("0")))
    )
    stock_by_sku = {row["sku"]: row["total"] for row in quant_qs}

    alert_mins: dict[str, Decimal] = {}
    for alert in StockAlert.objects.filter(sku__in=skus, is_active=True):
        alert_mins[alert.sku] = alert.min_quantity

    enriched = []
    for item in items:
        item = dict(item)
        sku = item.get("sku", "")
        available = stock_by_sku.get(sku, Decimal("0"))

        if available <= 0:
            item["stock_warning"] = "Sem estoque"
        elif sku in alert_mins and available < alert_mins[sku]:
            item["stock_warning"] = f"Últimas {int(available)} un."

        enriched.append(item)

    return enriched


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


def _format_datetime(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%d/%m às %H:%M")
