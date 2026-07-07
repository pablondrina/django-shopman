"""OrderQueueProjection — read models for the operator order queue (Fase 4).

Translates the active order queue into immutable projections for the operator
dashboard. Replaces the inline ``_enrich_order`` / ``_status_counts`` logic
from ``shopman.backstage.views.orders``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.utils import timezone
from shopman.orderman.models import Order
from shopman.utils.monetary import format_money

from shopman.backstage.presentation.status import (
    order_status_label,
    payment_method_label,
    status_color,
)
from shopman.shop.projections.types import (
    OrderItemProjection,
    TimelineEventProjection,
)
from shopman.shop.services import operator_orders
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

NEXT_ACTION_LABELS: dict[str, str] = {
    "confirmed": "Iniciar preparo",
    "preparing": "Marcar pronto",
    "ready": "Marcar como Retirado",
    "dispatched": "Marcar como Entregue",
    "delivered": "Concluir",
}

READY_DELIVERY_LABEL = "Marcar saída para entrega"


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AwaitingWorkOrderProjection:
    """A compact production dependency shown on order cards and detail."""

    ref: str
    status: str
    status_label: str
    output_sku: str
    planned_qty: str
    finished_qty: str
    progress_pct: int


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
    created_at_iso: str
    server_now_iso: str
    elapsed_seconds: int
    timer_class: str  # "timer-ok", "timer-warning", "timer-urgent", "timer-muted"
    items_summary: str
    items_count: int
    total_display: str
    fulfillment_icon: str  # Material Symbol ligature
    fulfillment_label: str
    fulfillment_type: str  # "delivery" | "pickup" — eixo de triagem no board
    can_confirm: bool
    can_advance: bool
    next_status: str
    next_action_label: str
    payment_method: str
    payment_method_label: str
    payment_status: str
    payment_pending: bool
    can_settle_delivery_cash: bool
    fiscal_status_label: str
    fiscal_status: str
    has_notes: bool
    assigned_operator: str
    awaiting_work_orders: tuple[AwaitingWorkOrderProjection, ...]
    # Prazo da confirmação otimista (só em pedidos NEW com timer agendado). Vazio
    # quando não há timer (confirmação manual, fora de NEW). O gestor renderiza um
    # countdown para o cliente não ficar no escuro sobre o prazo.
    confirmation_deadline_iso: str = ""
    confirmation_action: str = ""  # "confirm" | "cancel" — ação do directive ao vencer


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
    kitchen_note: str
    payment_method: str
    payment_method_label: str
    payment_status: str
    can_settle_delivery_cash: bool
    fiscal_status_label: str
    fiscal_status: str
    fiscal_links: tuple[dict[str, str], ...]
    awaiting_work_orders: tuple[AwaitingWorkOrderProjection, ...]
    is_gift: bool
    gift_recipient_name: str
    gift_recipient_phone: str
    gift_message: str
    gift_hide_values: bool
    cancellation_presets: tuple[str, ...]
    kitchen_note_tags: tuple[str, ...]


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
    payment_status = _payment_status(order)
    payment_method_label = _payment_method_label(method, payment_data)
    fiscal_status, fiscal_status_label, fiscal_links = _fiscal_status(order)

    recipient = order.data.get("recipient") if isinstance(order.data.get("recipient"), dict) else {}

    return OperatorOrderProjection(
        ref=order.ref,
        status=order.status,
        status_label=order_status_label(order.status),
        status_color=status_color(order.status),
        customer_name=customer_name,
        channel_ref=order.channel_ref or "",
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        fulfillment_label="Delivery" if _is_delivery(order) else "Retirada",
        total_display=_money(order.total_q),
        items=items,
        timeline=timeline,
        kitchen_note=order.data.get("kitchen_note", ""),
        payment_method=method,
        payment_method_label=payment_method_label,
        payment_status=payment_status,
        can_settle_delivery_cash=_can_settle_delivery_cash(order, payment_data),
        fiscal_status=fiscal_status,
        fiscal_status_label=fiscal_status_label,
        fiscal_links=fiscal_links,
        awaiting_work_orders=_awaiting_work_orders(order),
        is_gift=bool(order.data.get("is_gift")),
        gift_recipient_name=str(recipient.get("name", "") or ""),
        gift_recipient_phone=str(recipient.get("phone", "") or ""),
        gift_message=str(order.data.get("gift_message", "") or ""),
        gift_hide_values=bool(order.data.get("gift_hide_values")),
        cancellation_presets=_cancellation_presets(),
        kitchen_note_tags=_kitchen_note_tags(),
    )


def _cancellation_presets() -> tuple[str, ...]:
    """Store-configured reject/cancel justification presets (Admin/Unfold).

    The operator injects one with a tap in the gestor; the chosen text is sent to
    the customer in the cancellation notification. Read from the Shop singleton;
    never fails the projection.
    """
    try:
        from shopman.shop.models import Shop

        presets = Shop.load().cancellation_presets or []
    except Exception:
        logger.debug("orders.cancellation_presets_read_failed", exc_info=True)
        return ()
    return tuple(str(p).strip() for p in presets if str(p).strip())


def _kitchen_note_tags() -> tuple[str, ...]:
    """Store-configured kitchen-note tags (Admin/Unfold).

    The operator appends one with a tap in the gestor; the resulting note is shown
    on the KDS ticket for the kitchen. Read from the Shop singleton; never fails
    the projection.
    """
    try:
        from shopman.shop.models import Shop

        tags = Shop.load().kitchen_note_tags or []
    except Exception:
        logger.debug("orders.kitchen_note_tags_read_failed", exc_info=True)
        return ()
    return tuple(str(t).strip() for t in tags if str(t).strip())


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

    new_orders = [o for o in all_orders if o.status == "new"]
    deadlines = _confirmation_deadlines([o.ref for o in new_orders])
    entrada = tuple(_build_card(o, deadline=deadlines.get(o.ref)) for o in new_orders)
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


def _confirmation_deadlines(refs: list[str]) -> dict[str, tuple[str, str]]:
    """{order_ref: (expires_at_iso, action)} dos timers de confirmação pendentes.

    Batch (sem N+1): busca os directives confirmation.timeout queued uma vez e
    filtra em Python (normalmente há poucos pendentes)."""
    if not refs:
        return {}
    from shopman.orderman.models import Directive

    out: dict[str, tuple[str, str]] = {}
    # Filtra no DB pelos refs em questão (não traz TODOS os timers queued) — casa
    # a query ao conjunto pequeno de pedidos NEW mesmo se a fila acumular.
    directives = (
        Directive.objects.filter(
            topic="confirmation.timeout", status="queued", payload__order_ref__in=list(refs)
        )
        .order_by("available_at", "id")
    )
    for d in directives:
        ref = (d.payload or {}).get("order_ref")
        if ref and ref not in out:
            out[ref] = (str((d.payload or {}).get("expires_at") or ""), str((d.payload or {}).get("action") or ""))
    return out


def _build_card(order: Order, deadline: tuple[str, str] | None = None) -> OrderCardProjection:
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

    next_status = (
        operator_orders.next_status_for(order)
        if not operator_orders.advance_block_reason(order)
        else ""
    )
    next_label = _next_label(order)

    payment_data = order.data.get("payment", {})
    method = payment_data.get("method", "")
    payment_status = _payment_status(order)
    payment_method_label = _payment_method_label(method, payment_data)
    fiscal_status, fiscal_status_label, _fiscal_links = _fiscal_status(order)

    return OrderCardProjection(
        ref=order.ref,
        status=order.status,
        status_label=order_status_label(order.status),
        status_color=status_color(order.status),
        channel_ref=order.channel_ref or "",
        channel_icon=CHANNEL_ICONS.get(order.channel_ref or "", _DEFAULT_CHANNEL_ICON),
        customer_name=customer_name,
        created_at_display=_format_datetime(order.created_at),
        created_at_iso=order.created_at.isoformat(),
        server_now_iso=now.isoformat(),
        elapsed_seconds=int(elapsed),
        timer_class=timer_class,
        items_summary=items_summary,
        items_count=items_count,
        total_display=_money(order.total_q),
        fulfillment_icon=fulfillment_icon,
        fulfillment_label=fulfillment_label,
        fulfillment_type="delivery" if is_delivery else "pickup",
        can_confirm=order.status == "new",
        can_advance=bool(next_status),
        next_status=next_status,
        next_action_label=next_label,
        payment_method=method,
        payment_method_label=payment_method_label,
        payment_status=payment_status,
        payment_pending=_is_payment_pending(order, method, payment_status),
        can_settle_delivery_cash=_can_settle_delivery_cash(order, payment_data),
        fiscal_status_label=fiscal_status_label,
        fiscal_status=fiscal_status,
        has_notes=bool(order.data.get("kitchen_note")),
        assigned_operator=str((order.data.get("assignment") or {}).get("operator_name") or ""),
        awaiting_work_orders=_awaiting_work_orders(order),
        confirmation_deadline_iso=deadline[0] if deadline else "",
        confirmation_action=deadline[1] if deadline else "",
    )


def _awaiting_work_orders(order: Order) -> tuple[AwaitingWorkOrderProjection, ...]:
    refs = tuple(dict.fromkeys((order.data or {}).get("awaiting_wo_refs") or ()))
    if not refs:
        return ()

    try:
        from shopman.craftsman.models import WorkOrder

        from shopman.backstage.projections.production import WO_STATUS_LABELS, _qty, _work_order_progress_pct
    except Exception:
        logger.debug("orders.awaiting_work_orders_import_failed order=%s", order.ref, exc_info=True)
        return ()

    work_orders = WorkOrder.objects.filter(ref__in=refs).select_related("recipe").prefetch_related("events")
    by_ref = {wo.ref: wo for wo in work_orders}
    result: list[AwaitingWorkOrderProjection] = []
    for ref in refs:
        wo = by_ref.get(ref)
        if not wo:
            continue
        result.append(
            AwaitingWorkOrderProjection(
                ref=wo.ref,
                status=wo.status,
                status_label=WO_STATUS_LABELS.get(wo.status, wo.status),
                output_sku=wo.output_sku,
                planned_qty=_qty(wo.quantity),
                finished_qty=_qty(wo.finished) if wo.finished is not None else "",
                progress_pct=_work_order_progress_pct(wo),
            )
        )
    return tuple(result)


def _is_payment_pending(order: Order, method: str, payment_status: str) -> bool:
    """True when the order needs payment capture before physical work can start."""
    if order.status not in {"new", "confirmed"}:
        return False
    if method in _OFFLINE_METHODS:
        return False
    if order.status == "new" and not ((order.data or {}).get("payment") or {}).get("intent_ref"):
        return False
    return payment_status not in _PAYMENT_COMPLETE


def _payment_status(order: Order) -> str:
    """Return the operator-facing payment status without duplicating Payman."""
    return payment_svc.get_payment_status(order) or ""


def _payment_method_label(method: str, payment_data: dict) -> str:
    label = payment_method_label(method)
    if payment_data.get("collection") == "on_delivery":
        if payment_data.get("cod_settled_at"):
            return f"{label} entregue no caixa"
        return f"{label} na entrega"
    return label


def _can_settle_delivery_cash(order: Order, payment_data: dict) -> bool:
    return (
        _is_delivery(order)
        and payment_data.get("method") == "cash"
        and payment_data.get("collection") == "on_delivery"
        and not payment_data.get("cod_settled_at")
        and order.status in {Order.Status.DISPATCHED, Order.Status.DELIVERED, Order.Status.COMPLETED}
    )


def _fiscal_status(order: Order) -> tuple[str, str, tuple[dict[str, str], ...]]:
    data = order.data or {}
    if data.get("nfce_cancelled"):
        status = "cancelled"
        label = "NFC-e cancelada"
    elif data.get("nfce_access_key"):
        status = "authorized"
        label = "NFC-e autorizada"
    elif not ((data.get("fiscal") or {}).get("issue_document")):
        status = "not_requested"
        label = "Fiscal não solicitado"
    else:
        directive_status = _latest_fiscal_directive_status(order.ref)
        if directive_status == "failed":
            status = "failed"
            label = "NFC-e com falha"
        elif directive_status in {"queued", "running"}:
            status = "pending"
            label = "NFC-e pendente"
        elif order.status != Order.Status.COMPLETED:
            status = "waiting_completion"
            label = "Fiscal na conclusão"
        else:
            status = "pending"
            label = "NFC-e pendente"

    links = []
    if data.get("nfce_danfe_url"):
        links.append({"label": "DANFE", "url": data["nfce_danfe_url"]})
    if data.get("nfce_qrcode_url"):
        links.append({"label": "QR Code", "url": data["nfce_qrcode_url"]})
    return status, label, tuple(links)


def _latest_fiscal_directive_status(order_ref: str) -> str:
    try:
        from shopman.orderman.models import Directive

        from shopman.shop.directives import FISCAL_EMIT_NFCE
    except Exception:
        logger.debug("orders.fiscal_directive_import_failed order_ref=%s", order_ref, exc_info=True)
        return ""
    directive = (
        Directive.objects.filter(topic=FISCAL_EMIT_NFCE, payload__order_ref=order_ref)
        .order_by("-created_at")
        .first()
    )
    return directive.status if directive else ""


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
            return f"({ddd}) {number[:5]}-{number[5:]}"
        if len(number) == 8:
            return f"({ddd}) {number[:4]}-{number[4:]}"

    if label.startswith("+"):
        return "+" + digits

    if len(digits) == 11:
        return f"({digits[:2]}) {digits[2:7]}-{digits[7:]}"
    if len(digits) == 10:
        return f"({digits[:2]}) {digits[2:6]}-{digits[6:]}"

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


_EVENT_LABELS = {
    "operator_comment": "Comentário",
    "order_assigned": "Atendimento assumido",
    "order_unassigned": "Atendimento liberado",
}


def _build_timeline(order: Order) -> tuple[TimelineEventProjection, ...]:
    events = order.events.order_by("seq")
    result: list[TimelineEventProjection] = []
    for event in events:
        payload = event.payload or {}
        new_status = payload.get("new_status", "")
        if event.type == "status_changed" and new_status:
            label = order_status_label(new_status)
        elif event.type in _EVENT_LABELS:
            label = _EVENT_LABELS[event.type]
        else:
            label = event.type.replace("_", " ").title()

        result.append(
            TimelineEventProjection(
                label=label,
                event_type=event.type,
                timestamp_display=_format_datetime(event.created_at),
                actor=event.actor,
                detail=_event_detail(payload),
            )
        )
    return tuple(result)


def _event_detail(payload: dict) -> str:
    if not payload:
        return ""
    old_status = payload.get("old_status")
    new_status = payload.get("new_status")
    if old_status or new_status:
        old_label = order_status_label(old_status, old_status or "-")
        new_label = order_status_label(new_status, new_status or "-")
        return f"{old_label} -> {new_label}"
    for key in ("reason", "note", "error"):
        value = payload.get(key)
        if value:
            return str(value)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _money(value_q: int | None) -> str:
    if not value_q:
        return "R$ 0,00"
    return f"R$ {format_money(int(value_q))}"


def _format_datetime(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%d/%m às %H:%M")
