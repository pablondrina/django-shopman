"""Order tracking — storefront Presentation.

Consumes the data Projection (``shop.projections.order_tracking``) plus the copy
catalog (``shop.projections.copy``) and produces the display shape the tracking
templates and the storefront REST surface consume: resolved copy, money
formatted ``R$``, ETA phrase, status label + colour token, timeline labels,
progress labels, pickup hours. **No policy** is decided here — every decision
(status semantics, promise state, progress path) already arrived sealed in the
data projection.

This module owns the *appearance* DTOs (``OrderTrackingProjection`` &c). The
canonical copy lives in the orchestrator (``OMOTENASHI_DEFAULTS``); the strings
passed to ``catalog.title``/``catalog.message`` are last-resort fallbacks (per
the approved copy.py contract: fallback PT-BR lives in Presentation).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.utils.monetary import format_money

from shopman.shop.projections.copy import CopyCatalog, build_copy
from shopman.shop.projections.order_tracking import (
    TrackingData,
    TrackingFulfillmentData,
    TrackingPickupData,
    TrackingPromiseData,
    TrackingStatusData,
    build_tracking,
    build_tracking_status,
)
from shopman.shop.projections.types import (
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    Action,
    OrderItemProjection,
    TimelineEventProjection,
)
from shopman.storefront.presentation.types import (
    FulfillmentProjection,
    OrderProgressStepProjection,
)

logger = logging.getLogger(__name__)

DEFAULT_STATUS_COLOR = "bg-surface-alt text-on-surface/60 border border-outline"

# Surface display labels for timeline events that are not status changes.
EVENT_LABELS: dict[str, str | None] = {
    "created": "Pedido criado",
    "status_changed": None,
    "payment.captured": "Pagamento confirmado",
    "payment.refunded": "Pagamento estornado",
    "return_initiated": "Devolução solicitada",
    "refund_processed": "Reembolso processado",
    "fiscal_cancelled": "Nota fiscal cancelada",
    "fulfillment.dispatched": "Saiu para entrega",
    "fulfillment.delivered": "Pedido entregue",
}

FULFILLMENT_STATUS_LABELS: dict[str, str] = {
    "pending": "Aguardando",
    "in_progress": "Em separação",
    "dispatched": "Saiu para entrega",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}

# display_status_key → (copy key, fallback). Keys absent here fall back to the
# canonical order status labels.
STATUS_LABEL_COPY: dict[str, tuple[str, str]] = {
    "payment_expired": ("TRACKING_STATUS_PAYMENT_EXPIRED", "Pagamento expirado"),
    "waiting_store_confirmation": ("TRACKING_STATUS_WAITING_STORE_CONFIRMATION", "Aguardando confirmação"),
    "payment_pending": ("TRACKING_STATUS_PAYMENT_PENDING", "Aguardando pagamento"),
    "card_authorized": ("TRACKING_STATUS_CARD_AUTHORIZED", "Pagamento autorizado"),
    "ready_delivery": ("TRACKING_STATUS_READY_DELIVERY", "Aguardando entregador"),
    "ready_pickup": ("TRACKING_STATUS_READY_PICKUP", "Pronto para retirada"),
}

# Semantic payment status descriptor → customer-facing label.
PAYMENT_STATUS_LABELS: dict[str, str] = {
    "payment_expired": "Prazo para pagamento expirado",
    "payment_confirmed": "Pagamento confirmado",
    "card_authorized": "Pagamento autorizado",
    "payment_pending": "Aguardando confirmação do pagamento",
}

# Progress step key → (copy key, fallback).
STEP_LABEL_COPY: dict[str, tuple[str, str]] = {
    "received": ("TRACKING_STEP_RECEIVED", "Recebemos seu pedido."),
    "availability": ("TRACKING_STEP_AVAILABILITY_CONFIRMED", "Confirmamos a disponibilidade."),
    "payment": ("TRACKING_STEP_PAYMENT_CONFIRMED", "Reconhecemos o pagamento."),
    "preparing": ("TRACKING_STEP_PREPARING", "Estamos preparando seu pedido."),
    "ready_delivery": ("TRACKING_STEP_READY_DELIVERY", "Seu pedido está pronto e aguardando entregador."),
    "dispatched": ("TRACKING_STEP_DISPATCHED", "Seu pedido saiu para entrega."),
    "delivered": ("TRACKING_STEP_DELIVERED", "Seu pedido foi entregue."),
    "completed": ("TRACKING_STEP_COMPLETED", "O pedido foi concluído."),
    "cancelled": ("TRACKING_STEP_CANCELLED", "O pedido foi cancelado."),
}

DAY_NAMES_PT = {
    "monday": "Segunda",
    "tuesday": "Terça",
    "wednesday": "Quarta",
    "thursday": "Quinta",
    "friday": "Sexta",
    "saturday": "Sábado",
    "sunday": "Domingo",
}
DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


# ──────────────────────────────────────────────────────────────────────
# Presentation DTOs (appearance) — what templates / serializers consume
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PickupInfoProjection:
    """Store address and hours shown when the fulfillment type is pickup."""

    heading: str
    address: str
    opening_hours: str
    directions_label: str
    directions_url: str | None


@dataclass(frozen=True)
class OrderTrackingCopyProjection:
    """Surface chrome copy for the tracking page."""

    page_kicker: str
    order_ref_label: str
    menu_label: str
    support_label: str
    progress_heading: str
    live_badge: str
    polling_badge: str
    finished_badge: str
    items_heading: str
    total_label: str
    delivery_fee_label: str
    promise_fallback_message: str
    payment_confirmed_notice: str
    retry_label: str
    not_found_title: str
    not_found_description: str
    rate_limit_title: str
    cancel_success_title: str
    cancel_success_message: str
    cancel_failed_message: str
    mock_payment_success_title: str
    mock_payment_success_message: str
    mock_payment_failed_title: str
    mock_payment_failed_message: str
    rating_success_title: str
    rating_failed_message: str
    rating_comment_placeholder: str
    rating_comment_aria_label: str
    rating_submit_label: str


@dataclass(frozen=True)
class OrderTrackingPromiseProjection:
    """Current operational promise as rendered for the customer."""

    state: str
    title: str
    message: str
    tone: str
    deadline_at: str | None
    deadline_kind: str | None
    timer_mode: str
    deadline_action: str
    requires_active_notification: bool
    notification_topic: str | None
    actions: tuple[Action, ...] = ()
    next_event: str = ""
    recovery: str = ""
    active_notification: str = ""


@dataclass(frozen=True)
class OrderTrackingPromiseRowProjection:
    """One customer-facing promise detail row."""

    label: str
    value: str
    url: str | None = None


@dataclass(frozen=True)
class OrderTrackingProjection:
    """Canonical full tracking projection, rendered."""

    order_ref: str
    status: str
    status_label: str
    status_color: str
    copy: OrderTrackingCopyProjection
    promise: OrderTrackingPromiseProjection
    promise_rows: tuple[OrderTrackingPromiseRowProjection, ...]
    promise_deadline_label: str
    progress_steps: tuple[OrderProgressStepProjection, ...]
    timeline: tuple[TimelineEventProjection, ...]
    items: tuple[OrderItemProjection, ...]
    total_display: str
    delivery_fee_display: str | None
    is_delivery: bool
    delivery_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_info: PickupInfoProjection | None
    actions: tuple[Action, ...]
    is_active: bool
    server_now_iso: str
    payment_pending: bool
    payment_expired: bool
    payment_confirmed: bool
    show_payment_confirmed_notice: bool
    payment_status_label: str | None
    payment_expires_at: str | None
    confirmation_countdown: bool
    confirmation_expires_at: str | None
    eta_display: str | None
    whatsapp_url: str
    support_url: str
    share_text: str
    is_debug: bool
    last_updated_iso: str
    last_updated_display: str
    stale_after_seconds: int


@dataclass(frozen=True)
class OrderTrackingStatusProjection:
    """Polling projection for tracking status partials, rendered."""

    order_ref: str
    status: str
    status_label: str
    status_color: str
    progress_steps: tuple[OrderProgressStepProjection, ...]
    timeline: tuple[TimelineEventProjection, ...]
    is_terminal: bool


# ──────────────────────────────────────────────────────────────────────
# Entry points
# ──────────────────────────────────────────────────────────────────────


def build_order_tracking(order) -> OrderTrackingProjection:
    """Build the full tracking page projection for an Order."""
    from django.conf import settings

    return present_tracking(build_tracking(order, is_debug=settings.DEBUG))


def build_order_tracking_status(order) -> OrderTrackingStatusProjection:
    """Build the polling partial projection for an Order."""
    return present_tracking_status(build_tracking_status(order))


def present_tracking(data: TrackingData) -> OrderTrackingProjection:
    copy = build_copy("TRACKING")
    last_updated_display = copy.title("TRACKING_PROMISE_UPDATED_NOW", "Atualizado agora")
    promise = _present_promise(data.promise, status=data.status, is_delivery=data.is_delivery, copy=copy)
    return OrderTrackingProjection(
        order_ref=data.order_ref,
        status=data.status,
        status_label=_status_label(data.display_status_key, data.status, copy),
        status_color=ORDER_STATUS_COLORS.get(data.status, DEFAULT_STATUS_COLOR),
        copy=_tracking_copy(copy),
        promise=promise,
        promise_rows=_build_promise_rows(promise, last_updated_display=last_updated_display, copy=copy),
        promise_deadline_label=_clean_label(copy.title("TRACKING_PROMISE_LABEL_DEADLINE", "Prazo")),
        progress_steps=_present_progress_steps(data, copy=copy),
        timeline=_present_timeline(data),
        items=_present_items(data),
        total_display=f"R$ {format_money(data.total_q)}",
        delivery_fee_display=_delivery_fee_display(data.delivery_fee_q),
        is_delivery=data.is_delivery,
        delivery_fulfillments=_present_fulfillments(data.delivery_fulfillments, copy=copy),
        pickup_fulfillments=_present_fulfillments(data.pickup_fulfillments, copy=copy),
        pickup_info=_present_pickup(data.pickup, copy=copy),
        actions=data.actions,
        is_active=data.is_active,
        server_now_iso=data.server_now_iso,
        payment_pending=data.payment_pending,
        payment_expired=data.payment_expired,
        payment_confirmed=data.payment_confirmed,
        show_payment_confirmed_notice=data.show_payment_confirmed_notice,
        payment_status_label=_payment_status_label(data.payment_status_key),
        payment_expires_at=data.payment_expires_at,
        confirmation_countdown=data.confirmation_countdown,
        confirmation_expires_at=data.confirmation_expires_at,
        eta_display=_eta_display(data.eta_at),
        whatsapp_url=data.whatsapp_url,
        support_url=_support_url(data.support_url, data.order_ref, copy=copy),
        share_text=f"Meu pedido {data.order_ref} na {data.shop_name}",
        is_debug=data.is_debug,
        last_updated_iso=data.last_updated_iso,
        last_updated_display=last_updated_display,
        stale_after_seconds=data.stale_after_seconds,
    )


def present_tracking_status(data: TrackingStatusData) -> OrderTrackingStatusProjection:
    copy = build_copy("TRACKING")
    return OrderTrackingStatusProjection(
        order_ref=data.order_ref,
        status=data.status,
        status_label=_status_label(data.display_status_key, data.status, copy),
        status_color=ORDER_STATUS_COLORS.get(data.status, DEFAULT_STATUS_COLOR),
        progress_steps=_present_progress_steps_from(data.progress_steps, is_pickup=False, copy=copy),
        timeline=_present_timeline(data),
        is_terminal=data.is_terminal,
    )


# ──────────────────────────────────────────────────────────────────────
# Status, payment, money, ETA
# ──────────────────────────────────────────────────────────────────────


def _status_label(display_status_key: str, status: str, copy: CopyCatalog) -> str:
    spec = STATUS_LABEL_COPY.get(display_status_key)
    if spec:
        return copy.title(spec[0], spec[1])
    return ORDER_STATUS_LABELS_PT.get(display_status_key, ORDER_STATUS_LABELS_PT.get(status, status))


def _payment_status_label(payment_status_key: str | None) -> str | None:
    if not payment_status_key:
        return None
    return PAYMENT_STATUS_LABELS.get(payment_status_key)


def _delivery_fee_display(delivery_fee_q: int | None) -> str | None:
    if delivery_fee_q is None:
        return None
    return "Grátis" if delivery_fee_q == 0 else f"R$ {format_money(delivery_fee_q)}"


def _eta_display(eta_at: str | None) -> str | None:
    if not eta_at:
        return None
    dt = parse_datetime(eta_at)
    if dt is None:
        return None
    try:
        return timezone.localtime(dt).strftime("%H:%M")
    except Exception:
        logger.debug("order_tracking._eta_display degraded", exc_info=True)
        return None


def _fmt_timestamp(iso: str | None) -> str:
    if not iso:
        return ""
    dt = parse_datetime(iso)
    if dt is None:
        return str(iso)
    try:
        return timezone.localtime(dt).strftime("%d/%m às %H:%M")
    except Exception:
        logger.debug("order_tracking._fmt_timestamp degraded", exc_info=True)
        return str(iso)


def _clean_label(value: str) -> str:
    return str(value or "").strip().rstrip(":").strip()


def _support_url(base: str, order_ref: str, *, copy: CopyCatalog) -> str:
    if not base:
        return base
    support_message = copy.message(
        "TRACKING_SUPPORT_WHATSAPP_MESSAGE",
        "Oi! Posso ajudar com o pedido {order_ref}?",
    ).format(order_ref=order_ref)
    separator = "&" if "?" in base else "?"
    return f"{base}{separator}{urlencode({'text': support_message})}"


# ──────────────────────────────────────────────────────────────────────
# Promise
# ──────────────────────────────────────────────────────────────────────


def _present_promise(
    data: TrackingPromiseData,
    *,
    status: str,
    is_delivery: bool,
    copy: CopyCatalog,
) -> OrderTrackingPromiseProjection:
    title, message, next_event, recovery, active_notification = _promise_copy(
        data,
        status=status,
        is_delivery=is_delivery,
        copy=copy,
    )
    return OrderTrackingPromiseProjection(
        state=data.state,
        title=title,
        message=message,
        tone=data.tone,
        deadline_at=data.deadline_at,
        deadline_kind=data.deadline_kind,
        timer_mode=data.timer_mode,
        deadline_action=data.deadline_action,
        requires_active_notification=data.requires_active_notification,
        notification_topic=data.notification_topic,
        actions=data.actions,
        next_event=next_event,
        recovery=recovery,
        active_notification=active_notification,
    )


def _promise_copy(
    data: TrackingPromiseData,
    *,
    status: str,
    is_delivery: bool,
    copy: CopyCatalog,
) -> tuple[str, str, str, str, str]:
    """Return (title, message, next_event, recovery, active_notification)."""
    state = data.state

    if state == "payment_expired":
        title, message = _pair(copy, "TRACKING_PAYMENT_EXPIRED",
                               "O prazo para pagamento expirou.",
                               "O pedido foi automaticamente cancelado.")
        return title, message, "", "", ""

    if state in {"payment_requested", "payment_pending"}:
        if state == "payment_requested":
            title, message = _pair(copy, "TRACKING_PAYMENT_REQUESTED",
                                   "Disponibilidade confirmada.",
                                   "Para continuar, conclua o pagamento.")
        else:
            title, message = _pair(copy, "TRACKING_PAYMENT_PENDING",
                                   "Recebemos seu pedido.",
                                   "Aguardamos a confirmação do pagamento.")
        active = (
            copy.message(
                "TRACKING_PROMISE_PAYMENT_ACTIVE_NOTIFICATION",
                "Também avisamos por um canal ativo habilitado, porque o PIX depende da sua ação.",
            )
            if state == "payment_requested"
            else ""
        )
        return (
            title,
            message,
            copy.message("TRACKING_PROMISE_PAYMENT_NEXT", "Depois do pagamento, seguimos com o pedido."),
            copy.message(
                "TRACKING_PROMISE_PAYMENT_RECOVERY",
                "Se o prazo expirar, o pedido será cancelado automaticamente e o estoque reservado será liberado.",
            ),
            active,
        )

    if state == "availability_deferred":
        if data.next_opening_phrase:
            prefix = copy.message("TRACKING_PROMISE_CLOSED_HOURS_NEXT_PREFIX", "Próxima abertura:")
            next_event = f"{prefix} {data.next_opening_phrase}."
        else:
            next_event = copy.message(
                "TRACKING_PROMISE_CLOSED_HOURS_NEXT_UNKNOWN",
                "Atualizaremos o pedido assim que o próximo expediente estiver definido.",
            )
        return (
            copy.title("TRACKING_STEP_RECEIVED", "Recebemos seu pedido."),
            copy.message(
                "TRACKING_PROMISE_CLOSED_HOURS_MESSAGE",
                "Estamos fechados agora. Vamos conferir a disponibilidade quando abrirmos.",
            ),
            next_event,
            "",
            "",
        )

    if state == "card_authorized":
        next_event = (
            copy.message("TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_NEW", "O estabelecimento vai conferir a disponibilidade.")
            if status == "new"
            else copy.message(
                "TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_CONFIRMED",
                "Assim que a confirmação financeira terminar, seguimos com o pedido.",
            )
        )
        return (
            copy.title("TRACKING_CARD_AUTHORIZED", "Pagamento autorizado."),
            copy.message("TRACKING_CARD_AUTHORIZED", "Você não precisa fazer nada agora."),
            next_event,
            "",
            "",
        )

    if state == "availability_check":
        return (
            copy.title("TRACKING_STEP_RECEIVED", "Recebemos seu pedido."),
            "",
            "",
            copy.message(
                "TRACKING_PROMISE_AVAILABILITY_RECOVERY",
                "Se o estabelecimento não confirmar a tempo, atualizaremos o pedido aqui.",
            ),
            "",
        )

    if state == "payment_confirmed":
        next_event = (
            copy.message(
                "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_NEW",
                "O estabelecimento está conferindo a disponibilidade.",
            )
            if status == "new"
            else copy.message(
                "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_CONFIRMED",
                "Vamos começar o preparo do seu pedido.",
            )
        )
        return (
            copy.title("TRACKING_STEP_PAYMENT_CONFIRMED", "Reconhecemos o pagamento."),
            copy.message("TRACKING_PROMISE_PAYMENT_CONFIRMED_MESSAGE", "Nenhuma ação necessária agora."),
            next_event,
            "",
            "",
        )

    if state == "preparing":
        eta_display = _eta_display(data.eta_at)
        message = f"Previsão para ficar pronto às {eta_display}." if eta_display else ""
        next_event = (
            copy.message("TRACKING_PROMISE_PREPARING_NEXT_DELIVERY", "Quando estiver pronto, solicitaremos a coleta para entrega.")
            if is_delivery
            else copy.message("TRACKING_PROMISE_PREPARING_NEXT_PICKUP", "Quando estiver pronto, avisaremos você.")
        )
        return (
            copy.title("TRACKING_STEP_PREPARING", "Estamos preparando seu pedido."),
            message,
            next_event,
            "",
            "",
        )

    if state == "ready_delivery":
        title, message = _pair(copy, "TRACKING_DELIVERY_WAITING_COURIER",
                               "Aguardando entregador.",
                               "Já solicitamos a coleta do seu pedido. Assim que sair para entrega avisamos.")
        return (
            title,
            message,
            copy.message("TRACKING_PROMISE_READY_DELIVERY_NEXT", "Assim que sair para entrega, avisamos você."),
            "",
            "",
        )

    if state == "ready_pickup":
        return (
            copy.title("TRACKING_STEP_READY_PICKUP", "Seu pedido está pronto para retirada."),
            "",
            copy.message("TRACKING_PROMISE_READY_PICKUP_NEXT", "Retire no estabelecimento quando puder."),
            "",
            "",
        )

    terminal = _TERMINAL_PROMISE_COPY.get(state)
    if terminal:
        copy_key, fallback, message_key, message_fb, next_key, next_fb = terminal
        active = (
            copy.message("TRACKING_PROMISE_ACTIVE_UPDATE_NOTIFICATION", "Avisamos ativamente sobre esta atualização.")
            if state in {"dispatched", "delivered"}
            else ""
        )
        return (
            copy.title(copy_key, fallback),
            copy.message(message_key, message_fb) if message_key else message_fb,
            copy.message(next_key, next_fb) if next_key else next_fb,
            "",
            active,
        )

    return (
        copy.title("TRACKING_STEP_RECEIVED", "Recebemos seu pedido."),
        copy.message("TRACKING_PROMISE_AVAILABILITY_MESSAGE", "O estabelecimento está conferindo a disponibilidade."),
        copy.message("TRACKING_PROMISE_RECEIVED_NEXT", "O estabelecimento vai conferir a disponibilidade."),
        "",
        "",
    )


# state → (title_key, title_fb, message_key, message_fb, next_key, next_fb)
_TERMINAL_PROMISE_COPY: dict[str, tuple[str, str, str, str, str, str]] = {
    "dispatched": (
        "TRACKING_STEP_DISPATCHED", "Seu pedido saiu para entrega.",
        "TRACKING_PROMISE_DISPATCHED_MESSAGE", "Estamos acompanhando a entrega.",
        "TRACKING_PROMISE_DISPATCHED_NEXT", "Quando for entregue, atualizaremos o pedido.",
    ),
    "delivered": (
        "TRACKING_STEP_DELIVERED", "Seu pedido foi entregue.",
        "", "",
        "TRACKING_PROMISE_DELIVERED_NEXT", "O pedido será concluído em seguida.",
    ),
    "completed": (
        "TRACKING_STEP_COMPLETED", "O pedido foi concluído.",
        "", "", "", "",
    ),
    "cancelled": (
        "TRACKING_STEP_CANCELLED", "O pedido foi cancelado.",
        "", "", "", "",
    ),
}


def _pair(copy: CopyCatalog, key: str, fallback_title: str, fallback_message: str) -> tuple[str, str]:
    return copy.title(key, fallback_title), copy.message(key, fallback_message)


def _first_visible_action(actions: tuple[Action, ...]) -> Action | None:
    for action in actions:
        if action.enabled:
            return action
    return actions[0] if actions else None


def _build_promise_rows(
    promise: OrderTrackingPromiseProjection,
    *,
    last_updated_display: str,
    copy: CopyCatalog,
) -> tuple[OrderTrackingPromiseRowProjection, ...]:
    rows: list[OrderTrackingPromiseRowProjection] = []
    if promise.next_event:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(copy.title("TRACKING_PROMISE_LABEL_NEXT", "Próximo passo")),
            value=promise.next_event,
        ))
    visible_action = _first_visible_action(promise.actions)
    if visible_action:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(copy.title("TRACKING_PROMISE_LABEL_ACTION", "Sua ação")),
            value=visible_action.label,
            url=visible_action.href or None,
        ))
    if promise.recovery:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(copy.title("TRACKING_PROMISE_LABEL_RECOVERY", "Se algo mudar")),
            value=promise.recovery,
        ))
    if promise.requires_active_notification and promise.active_notification:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(copy.title("TRACKING_PROMISE_LABEL_ACTIVE_NOTIFICATION", "Aviso")),
            value=promise.active_notification,
        ))
    if last_updated_display:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(copy.title("TRACKING_PROMISE_LABEL_UPDATED", "Última atualização")),
            value=last_updated_display,
        ))
    return tuple(rows)


# ──────────────────────────────────────────────────────────────────────
# Items, timeline, progress, fulfillments, pickup
# ──────────────────────────────────────────────────────────────────────


def _present_items(data: TrackingData) -> tuple[OrderItemProjection, ...]:
    return tuple(
        OrderItemProjection(
            sku=item.sku,
            name=item.name,
            qty=item.qty,
            unit_price_display=f"R$ {format_money(item.unit_price_q)}",
            total_display=f"R$ {format_money(item.line_total_q)}",
        )
        for item in data.items
    )


def _timeline_label(event_type: str, label_key: str) -> str:
    if event_type == "status_changed" and label_key:
        return ORDER_STATUS_LABELS_PT.get(label_key, label_key)
    if label_key == "shipment_dispatched":
        return "Enviado"
    if label_key == "shipment_delivered":
        return "Entregue"
    label = EVENT_LABELS.get(event_type)
    if label is None:
        label = event_type.replace(".", " ").replace("_", " ").title()
    return label


def _present_timeline(data: TrackingData | TrackingStatusData) -> tuple[TimelineEventProjection, ...]:
    return tuple(
        TimelineEventProjection(
            label=_timeline_label(event.event_type, event.label_key),
            event_type=event.event_type,
            timestamp_display=_fmt_timestamp(event.at),
        )
        for event in data.timeline
    )


def _step_label(key: str, *, is_pickup: bool, copy: CopyCatalog) -> str:
    if key == "ready":
        if is_pickup:
            return copy.title("TRACKING_STEP_READY_PICKUP", "Seu pedido está pronto para retirada.")
        return copy.title("TRACKING_STEP_READY_GENERIC", "Seu pedido está pronto.")
    spec = STEP_LABEL_COPY.get(key)
    if spec:
        return copy.title(spec[0], spec[1])
    return key


def _present_progress_steps(data: TrackingData, *, copy: CopyCatalog) -> tuple[OrderProgressStepProjection, ...]:
    return _present_progress_steps_from(data.progress_steps, is_pickup=data.is_pickup, copy=copy)


def _present_progress_steps_from(steps, *, is_pickup: bool, copy: CopyCatalog) -> tuple[OrderProgressStepProjection, ...]:
    return tuple(
        OrderProgressStepProjection(
            label=_step_label(step.key, is_pickup=is_pickup, copy=copy),
            key=step.key,
            state=step.state,
            timestamp_display=_fmt_timestamp(step.at) if step.at else None,
        )
        for step in steps
    )


def _fulfillment_tracking_label(carrier: str | None, copy: CopyCatalog) -> str:
    if carrier:
        template = copy.title("TRACKING_TRACK_SHIPMENT_WITH_CARRIER", "Acompanhar via {carrier}")
        return template.format(carrier=carrier)
    return copy.title("TRACKING_TRACK_SHIPMENT", "Rastrear envio")


def _present_fulfillments(
    fulfillments: tuple[TrackingFulfillmentData, ...],
    *,
    copy: CopyCatalog,
) -> tuple[FulfillmentProjection, ...]:
    return tuple(
        FulfillmentProjection(
            status=ful.status,
            status_label=FULFILLMENT_STATUS_LABELS.get(ful.status, ful.status),
            tracking_label=_fulfillment_tracking_label(ful.carrier, copy),
            tracking_code=ful.tracking_code,
            tracking_url=ful.tracking_url,
            carrier=ful.carrier,
            dispatched_at_display=_fmt_timestamp(ful.dispatched_at) if ful.dispatched_at else None,
            delivered_at_display=_fmt_timestamp(ful.delivered_at) if ful.delivered_at else None,
        )
        for ful in fulfillments
    )


def _present_pickup(pickup: TrackingPickupData | None, *, copy: CopyCatalog) -> PickupInfoProjection | None:
    if pickup is None:
        return None
    return PickupInfoProjection(
        heading=copy.title("TRACKING_PICKUP_HEADING", "Retirada"),
        address=pickup.address,
        opening_hours=_format_opening_hours(pickup.opening_hours),
        directions_label=copy.title("TRACKING_PICKUP_DIRECTIONS_CTA", "Como chegar"),
        directions_url=pickup.directions_url,
    )


def _format_opening_hours(opening_hours: dict) -> str:
    if not opening_hours:
        return ""

    def _fmt_time(value: str) -> str:
        parts = value.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if minute:
            return f"{hour}h{minute:02d}"
        return f"{hour}h"

    day_hours: list[tuple[str, str]] = []
    for day in DAY_ORDER:
        info = opening_hours.get(day)
        if info and info.get("open") and info.get("close"):
            day_hours.append((day, f"{_fmt_time(info['open'])} — {_fmt_time(info['close'])}"))
        else:
            day_hours.append((day, "Fechado"))

    groups: list[tuple[list[str], str]] = []
    for day, hours in day_hours:
        if groups and groups[-1][1] == hours:
            groups[-1][0].append(day)
        else:
            groups.append(([day], hours))

    result = []
    for days, hours in groups:
        if len(days) == 1:
            label = DAY_NAMES_PT[days[0]]
        elif len(days) == 2:
            label = f"{DAY_NAMES_PT[days[0]]} e {DAY_NAMES_PT[days[1]]}"
        else:
            label = f"{DAY_NAMES_PT[days[0]]} a {DAY_NAMES_PT[days[-1]]}"
        result.append({"label": label, "hours": hours})
    return "; ".join(f"{hour['label']}: {hour['hours']}" for hour in result)


def _tracking_copy(copy: CopyCatalog) -> OrderTrackingCopyProjection:
    return OrderTrackingCopyProjection(
        page_kicker=copy.title("TRACKING_PAGE_KICKER", "Acompanhamento"),
        order_ref_label=copy.title("TRACKING_ORDER_REF_LABEL", "Pedido"),
        menu_label=copy.title("TRACKING_MENU_CTA", "Ver cardápio"),
        support_label=copy.title("TRACKING_SUPPORT_CTA", "Ajuda"),
        progress_heading=copy.title("TRACKING_PROGRESS_HEADING", "Progresso"),
        live_badge=copy.title("TRACKING_LIVE_BADGE", "Ao vivo"),
        polling_badge=copy.title("TRACKING_POLLING_BADGE", "Atualização periódica"),
        finished_badge=copy.title("TRACKING_FINISHED_BADGE", "Finalizado"),
        items_heading=copy.title("TRACKING_ITEMS_HEADING", "Itens do pedido"),
        total_label=copy.title("TRACKING_TOTAL_LABEL", "Total"),
        delivery_fee_label=copy.title("TRACKING_DELIVERY_FEE_LABEL", "Entrega"),
        promise_fallback_message=copy.message(
            "TRACKING_PROMISE_FALLBACK_MESSAGE",
            "Acompanhando atualizações do pedido.",
        ),
        payment_confirmed_notice=copy.message(
            "TRACKING_PAYMENT_CONFIRMED_NOTICE",
            "Pagamento confirmado. Acompanhe o próximo passo nesta página.",
        ),
        retry_label=copy.title("TRACKING_RETRY_CTA", "Tentar novamente"),
        not_found_title=copy.title("TRACKING_NOT_FOUND_TITLE", "Pedido não encontrado"),
        not_found_description=copy.message(
            "TRACKING_NOT_FOUND_MESSAGE",
            "Confira o link do pedido ou fale com a equipe.",
        ),
        rate_limit_title=copy.title("TRACKING_RATE_LIMIT_TITLE", "Atualização pausada por um instante"),
        cancel_success_title=copy.title("TRACKING_CANCEL_SUCCESS_TITLE", "Pedido cancelado"),
        cancel_success_message=copy.message(
            "TRACKING_CANCEL_SUCCESS_MESSAGE",
            "Recebemos o cancelamento. Acompanhe o status nesta página.",
        ),
        cancel_failed_message=copy.message(
            "TRACKING_CANCEL_FAILED_MESSAGE",
            "Não foi possível cancelar este pedido agora.",
        ),
        mock_payment_success_title=copy.title("TRACKING_MOCK_PAYMENT_SUCCESS_TITLE", "Pagamento teste capturado"),
        mock_payment_success_message=copy.message(
            "TRACKING_MOCK_PAYMENT_SUCCESS_MESSAGE",
            "Atualizamos o pedido com o estado financeiro simulado.",
        ),
        mock_payment_failed_title=copy.title(
            "TRACKING_MOCK_PAYMENT_FAILED_TITLE",
            "Não foi possível capturar o pagamento teste",
        ),
        mock_payment_failed_message=copy.message(
            "TRACKING_MOCK_PAYMENT_FAILED_MESSAGE",
            "Atualize o pedido e tente novamente.",
        ),
        rating_success_title=copy.title("TRACKING_RATING_SUCCESS_TITLE", "Avaliação registrada"),
        rating_failed_message=copy.message(
            "TRACKING_RATING_FAILED_MESSAGE",
            "Não foi possível registrar a avaliação agora.",
        ),
        rating_comment_placeholder=copy.title("TRACKING_RATING_COMMENT_PLACEHOLDER", "Comentário opcional"),
        rating_comment_aria_label=copy.title("TRACKING_RATING_COMMENT_ARIA_LABEL", "Comentário da avaliação"),
        rating_submit_label=copy.title("TRACKING_RATING_SUBMIT_CTA", "Enviar avaliação"),
    )


__all__ = [
    "OrderTrackingCopyProjection",
    "OrderTrackingProjection",
    "OrderTrackingPromiseProjection",
    "OrderTrackingPromiseRowProjection",
    "OrderTrackingStatusProjection",
    "PickupInfoProjection",
    "build_order_tracking",
    "build_order_tracking_status",
    "present_tracking",
    "present_tracking_status",
]
