"""KDSBoardProjection — read models for the Kitchen Display System (Fase 4).

Translates KDS instances, tickets, and expedition orders into immutable
projections. Replaces the inline ``_enrich_ticket`` / ``_enrich_expedition_order``
logic from ``shopman.backstage.views.kds``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.shop.services.order_helpers import get_fulfillment_type

from .order_queue import _DEFAULT_CHANNEL_ICON, CHANNEL_ICONS

logger = logging.getLogger(__name__)

ACTIVE_TICKET_STATUSES = ("pending", "in_progress")
RECENT_CANCELLED_WINDOW = timedelta(minutes=10)
RECENT_CANCELLED_LIMIT = 8
RECENT_DONE_WINDOW = timedelta(minutes=30)
RECENT_DONE_LIMIT = 12


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
    target_seconds: int  # target SLA in seconds (for K12 timer context)
    timer_class: str  # "timer-ok", "timer-warning", "timer-late"
    items: tuple[KDSItemProjection, ...]
    status: str
    all_checked: bool
    # Discriminante explícito da união ticket|expedição no front (nunca inferir por
    # presença de campo: foi o que quebrou a Expedição quando `items` passou a existir
    # nos dois). Ticket de preparo é sempre False.
    is_expedition: bool = False
    status_label: str = ""
    is_cancelled: bool = False
    cancelled_at_display: str = ""
    completed_at_display: str = ""
    # Order-level notes shown to the kitchen: the operator's kitchen note (from the
    # gestor) and the customer's checkout note (order_notes). Empty when absent.
    kitchen_note: str = ""
    customer_note: str = ""


@dataclass(frozen=True)
class KDSExpeditionCardProjection:
    """An order card in the expedition (dispatch) board."""

    pk: int
    order_ref: str
    channel_icon: str
    customer_name: str
    fulfillment_icon: str
    fulfillment_label: str
    is_delivery: bool
    units_count: str
    line_count: int
    total_display: str
    items: tuple[KDSItemProjection, ...] = ()
    # Discriminante explícito da união ticket|expedição (ver KDSTicketProjection).
    # Card de expedição é sempre True.
    is_expedition: bool = True


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
    cancelled_tickets: tuple[KDSTicketProjection, ...] = ()
    recent_done: tuple[KDSTicketProjection, ...] = ()  # para recall (desfazer finalização)


@dataclass(frozen=True)
class KDSCustomerOrderProjection:
    """Privacy-safe order status for a customer-facing ready board."""

    ref: str
    status: str
    status_label: str
    updated_at_display: str


@dataclass(frozen=True)
class KDSCustomerStatusProjection:
    """Customer-facing KDS status split by preparation and pickup readiness."""

    preparing: tuple[KDSCustomerOrderProjection, ...]
    ready: tuple[KDSCustomerOrderProjection, ...]
    updated_at_display: str


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
                status__in=ACTIVE_TICKET_STATUSES,
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

    active_qs = (
        KDSTicket.objects.filter(
            kds_instance=instance,
            status__in=ACTIVE_TICKET_STATUSES,
        )
                .order_by("created_at")
    )
    now = timezone.now()
    cancelled_qs = (
        KDSTicket.objects.filter(
            kds_instance=instance,
            status="cancelled",
            acknowledged_at__isnull=True,
            cancelled_at__gte=now - RECENT_CANCELLED_WINDOW,
        )
                .order_by("-cancelled_at", "-created_at")[:RECENT_CANCELLED_LIMIT]
    )
    done_qs = (
        KDSTicket.objects.filter(
            kds_instance=instance,
            status="done",
            completed_at__gte=now - RECENT_DONE_WINDOW,
        )
                .order_by("-completed_at")[:RECENT_DONE_LIMIT]
    )

    tickets = tuple(_build_ticket(t, instance) for t in active_qs)
    cancelled_tickets = tuple(_build_ticket(t, instance) for t in cancelled_qs)
    recent_done = tuple(_build_ticket(t, instance) for t in done_qs)
    pending = sum(1 for t in tickets if t.status == "pending")
    in_progress = sum(1 for t in tickets if t.status == "in_progress")

    return KDSBoardProjection(
        instance_ref=instance.ref,
        instance_name=instance.name,
        instance_type=instance.type,
        is_expedition=False,
        tickets=tickets,
        counts={
            "pending": pending,
            "in_progress": in_progress,
            "total": len(tickets),
            "cancelled_recent": len(cancelled_tickets),
            "done_recent": len(recent_done),
        },
        cancelled_tickets=cancelled_tickets,
        recent_done=recent_done,
    )


def build_kds_ticket(ticket_pk: int) -> KDSTicketProjection:
    """Build a single ticket projection (for HTMX partial re-renders)."""
    from shopman.backstage.models import KDSTicket

    ticket = KDSTicket.objects.select_related("kds_instance").get(pk=ticket_pk)
    return _build_ticket(ticket, ticket.kds_instance)


def build_kds_customer_status(*, limit: int = 24) -> KDSCustomerStatusProjection:
    """Build a public pickup board without customer names, phones, totals, or addresses."""
    orders_qs = (
        Order.objects.filter(
            status__in=[
                Order.Status.CONFIRMED,
                Order.Status.PREPARING,
                Order.Status.READY,
            ]
        )
        .order_by("ready_at", "updated_at", "created_at")[: max(limit * 2, limit)]
    )

    preparing: list[KDSCustomerOrderProjection] = []
    ready: list[KDSCustomerOrderProjection] = []

    for order in orders_qs:
        if get_fulfillment_type(order) == "delivery":
            continue
        projection = KDSCustomerOrderProjection(
            ref=order.ref,
            status=order.status,
            status_label="Pronto para retirar" if order.status == Order.Status.READY else "Em preparo",
            updated_at_display=_format_time(order.ready_at or order.updated_at or order.created_at),
        )
        if order.status == Order.Status.READY:
            ready.append(projection)
        else:
            preparing.append(projection)

        if len(preparing) + len(ready) >= limit:
            break

    return KDSCustomerStatusProjection(
        preparing=tuple(preparing),
        ready=tuple(ready),
        updated_at_display=_format_time(timezone.now()),
    )


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
        counts={
            "pending": len(cards),
            "in_progress": 0,
            "total": len(cards),
            "cancelled_recent": 0,
        },
    )


def _resolve_ticket_source(ticket):
    """Resolve a ticket's ``session_key`` to its current source for display.

    Returns the committed Order when it exists, otherwise the open Session
    (comanda fired progressively before commit). Both expose ``data`` /
    ``handle_ref`` / ``channel_ref``; ``ref`` only exists on Order, so the
    pre-commit comanda falls back to its handle (tab label) for the heading.

    An empty ``session_key`` is invalid (a real source always has one): it must
    never resolve, or every empty-key ticket would collapse onto the same
    arbitrary ``filter(session_key="").first()`` source.
    """
    from shopman.orderman.models import Session

    if not ticket.session_key:
        return None

    order = (
        Order.objects.filter(session_key=ticket.session_key)
        .order_by("-id")
        .first()
    )
    if order is not None:
        return order
    return (
        Session.objects.filter(session_key=ticket.session_key, state="open")
        .order_by("-id")
        .first()
    )


def _build_ticket(ticket, instance) -> KDSTicketProjection:
    now = timezone.now()
    is_cancelled = ticket.status == "cancelled"
    elapsed_until = ticket.cancelled_at if is_cancelled and ticket.cancelled_at else now
    elapsed = (elapsed_until - ticket.created_at).total_seconds()
    target_sec = instance.target_time_minutes * 60

    if elapsed < target_sec:
        timer_class = "timer-ok"
    elif elapsed < target_sec * 2:
        timer_class = "timer-warning"
    else:
        timer_class = "timer-late"

    source = _resolve_ticket_source(ticket)
    source_data = (getattr(source, "data", None) or {}) if source is not None else {}
    handle_ref = getattr(source, "handle_ref", "") if source is not None else ""
    order_ref = getattr(source, "ref", "") or handle_ref or ticket.session_key
    channel_ref = getattr(source, "channel_ref", "") if source is not None else ""
    customer_name = (
        source_data.get("customer", {}).get("name", "")
        or handle_ref
        or ""
    )
    fulfillment_type = source_data.get("fulfillment_type") or source_data.get("delivery_method", "")
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
        order_ref=order_ref,
        channel_icon=CHANNEL_ICONS.get(channel_ref or "", _DEFAULT_CHANNEL_ICON),
        customer_name=customer_name,
        fulfillment_icon=fulfillment_icon,
        created_at_display=_format_datetime(ticket.created_at),
        elapsed_seconds=int(elapsed),
        target_seconds=int(target_sec),
        timer_class=timer_class,
        items=items,
        status=ticket.status,
        all_checked=all(it.checked for it in items) if items else False,
        status_label=_ticket_status_label(ticket.status),
        is_cancelled=is_cancelled,
        cancelled_at_display=_format_time(ticket.cancelled_at),
        completed_at_display=_format_time(ticket.completed_at),
        kitchen_note=str(source_data.get("kitchen_note", "") or ""),
        customer_note=str(source_data.get("order_notes", "") or ""),
    )


def _ticket_status_label(status: str) -> str:
    labels = {
        "pending": "Pendente",
        "in_progress": "Em preparo",
        "done": "Concluído",
        "cancelled": "Cancelado",
    }
    return labels.get(status, status)


def _build_expedition_card(order: Order) -> KDSExpeditionCardProjection:
    customer_name = (
        order.data.get("customer", {}).get("name", "")
        or order.handle_ref
        or ""
    )
    is_delivery = get_fulfillment_type(order) == "delivery"
    items = tuple(order.items.all())
    units_count = sum((Decimal(str(item.qty)) for item in items), Decimal("0"))
    # Itens para conferência na expedição (despacho/entrega): qty × nome, sem check/SLA.
    item_projections = tuple(
        KDSItemProjection(
            sku=getattr(item, "sku", "") or "",
            name=getattr(item, "name", "") or getattr(item, "sku", "") or "",
            qty=int(Decimal(str(item.qty))),
            notes=str(getattr(item, "notes", "") or ""),
            checked=False,
            stock_warning="",
        )
        for item in items
    )

    return KDSExpeditionCardProjection(
        pk=order.pk,
        order_ref=order.ref,
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        customer_name=customer_name,
        fulfillment_icon="local_shipping" if is_delivery else "storefront",
        fulfillment_label="Delivery" if is_delivery else "Retirada",
        is_delivery=is_delivery,
        units_count=_qty(units_count),
        line_count=len(items),
        total_display=_money(order.total_q),
        items=item_projections,
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
        .filter(Q(target_date__isnull=True) | Q(target_date__lte=timezone.localdate()))
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


def _qty(value: Decimal) -> str:
    if not value:
        return "0"
    return format(value.quantize(Decimal("0.001")).normalize(), "f")


def _format_datetime(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%d/%m às %H:%M")


def _format_time(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%H:%M")
