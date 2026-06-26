"""Order tracking — read-side Projection of data (surface-agnostic).

This is the policy-laden, semantic read model for order tracking. It decides
*everything* the customer-facing surfaces need — status semantics, the promise
state machine, the progress path, payment state, fulfillment, ETA — and emits
it as **data**: enums/keys, ``_q`` cents, ISO timestamps, booleans, refs and
``Action`` items. It carries **no** rendered copy, money formatting, ETA phrase,
status label, colour token or HTML — those are Presentation, resolved per
surface in ``<surface>/presentation/order_tracking.py`` from this projection
plus the copy catalog (``shop.projections.copy``).

Actions carry resolved ``label`` strings (ADR-012: "copy curta pronta para a
superfície"), resolved here because the orchestrator owns copy
(``OMOTENASHI_DEFAULTS``); no money/locale/HTML formatting happens in this
module.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Directive

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.projections.interaction_context import InteractionContext
from shopman.shop.projections.types import Action
from shopman.shop.services import payment_status
from shopman.shop.services.business_calendar import (
    BusinessCalendarState,
    current_business_state,
    format_next_opening,
)

logger = logging.getLogger(__name__)

CARRIER_TRACKING_URLS: dict[str, str] = {
    "correios": "https://rastreamento.correios.com.br/?objetos={code}",
    "jadlog": "https://www.jadlog.com.br/tracking?code={code}",
}

TERMINAL_STATUSES = frozenset({"completed", "cancelled", "returned"})

STALE_AFTER_SECONDS = 45


# ──────────────────────────────────────────────────────────────────────
# Data DTOs — frozen, semantic, surface-agnostic
# ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TrackingItemData:
    """One ordered line — semantic, prices in cents."""

    sku: str
    name: str
    qty: int
    unit_price_q: int
    line_total_q: int


@dataclass(frozen=True)
class TrackingTimelineEventData:
    """One timeline event. ``label_key`` is the semantic discriminator the
    Presentation maps to a human label: the new status for ``status_changed``
    events, ``shipment_dispatched``/``shipment_delivered`` for fulfillment
    records, or empty (Presentation falls back to ``event_type``)."""

    event_type: str
    at: str  # ISO timestamp
    label_key: str = ""


@dataclass(frozen=True)
class TrackingProgressStepData:
    """One step of the customer-facing operational path."""

    key: str
    state: str  # completed | current | pending | cancelled
    at: str | None = None  # ISO timestamp the step was reached


@dataclass(frozen=True)
class TrackingFulfillmentData:
    """A fulfillment record (delivery or pickup) — semantic."""

    status: str
    tracking_code: str | None
    tracking_url: str | None
    carrier: str | None
    dispatched_at: str | None  # ISO
    delivered_at: str | None  # ISO


@dataclass(frozen=True)
class TrackingPickupData:
    """Pickup point as data — address, directions link, raw opening hours."""

    address: str
    directions_url: str | None
    opening_hours: dict[str, Any]  # raw Shop.opening_hours; Presentation formats


@dataclass(frozen=True)
class TrackingPromiseData:
    """The active operational promise as data.

    The promise *state machine* is policy and lives here; ``state`` plus the
    surrounding flags (``status``, ``is_delivery``) let Presentation pick the
    title/message/next-step copy. No rendered strings are stored.
    """

    state: str
    tone: str  # info | warning | danger | success
    deadline_at: str | None
    deadline_kind: str | None
    timer_mode: str
    deadline_action: str
    requires_active_notification: bool
    notification_topic: str | None
    actions: tuple[Action, ...] = ()
    eta_at: str | None = None  # ISO; preparing ETA
    next_opening_phrase: str = ""  # availability_deferred; resolved against business calendar


@dataclass(frozen=True)
class TrackingData:
    """Canonical full tracking projection — data only."""

    order_ref: str
    status: str
    display_status_key: str
    is_delivery: bool
    is_pickup: bool
    promise: TrackingPromiseData
    progress_steps: tuple[TrackingProgressStepData, ...]
    timeline: tuple[TrackingTimelineEventData, ...]
    items: tuple[TrackingItemData, ...]
    total_q: int
    delivery_fee_q: int | None
    delivery_distance_km: float | None
    delivery_fulfillments: tuple[TrackingFulfillmentData, ...]
    pickup_fulfillments: tuple[TrackingFulfillmentData, ...]
    pickup: TrackingPickupData | None
    actions: tuple[Action, ...]
    is_active: bool
    server_now_iso: str
    payment_pending: bool
    payment_expired: bool
    payment_confirmed: bool
    show_payment_confirmed_notice: bool
    payment_status_key: str | None
    payment_expires_at: str | None
    confirmation_countdown: bool
    confirmation_expires_at: str | None
    eta_at: str | None
    whatsapp_url: str
    support_url: str
    shop_name: str
    is_debug: bool
    last_updated_iso: str
    stale_after_seconds: int = STALE_AFTER_SECONDS


@dataclass(frozen=True)
class TrackingStatusData:
    """Polling projection for tracking status partials — data only."""

    order_ref: str
    status: str
    display_status_key: str
    progress_steps: tuple[TrackingProgressStepData, ...]
    timeline: tuple[TrackingTimelineEventData, ...]
    is_terminal: bool


# ──────────────────────────────────────────────────────────────────────
# Builders
# ──────────────────────────────────────────────────────────────────────


def build_tracking(order, *, is_debug: bool = False) -> TrackingData:
    """Build the full tracking data projection for an order."""
    interaction = InteractionContext.from_order(order, surface_ref="tracking")
    server_now = timezone.now()
    payment_expired = _is_payment_timeout_cancelled(order)
    items = _build_items(order)
    order_data = order.data or {}
    fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
    is_delivery = fulfillment_type == "delivery"
    is_pickup = fulfillment_type == "pickup"
    delivery_fulfillments, pickup_fulfillments = _build_fulfillments(
        order,
        is_delivery=is_delivery,
        is_pickup=is_pickup,
    )
    pickup = _pickup_data() if is_pickup else None

    delivery_fee_q = order_data.get("delivery_fee_q")
    delivery_distance_km = order_data.get("delivery_distance_km")
    delivery_distance_km = float(delivery_distance_km) if delivery_distance_km is not None else None

    payment_pending, payment_confirmed, payment_status_key, payment_expires_at = _payment_info(order)
    progress_steps = _build_progress_steps(
        order,
        is_delivery=is_delivery,
        is_pickup=is_pickup,
        payment_confirmed=payment_confirmed,
    )
    timeline = _build_timeline(order)
    business_state = current_business_state()
    confirmation_countdown, confirmation_expires_at = _confirmation_info(
        order,
        payment_pending=payment_pending,
        business_state=business_state,
    )
    whatsapp_url, support_url, shop_name = _contact_and_share(order)
    eta_at = _eta_at(order)
    promise = _build_promise(
        order,
        is_delivery=is_delivery,
        payment_pending=payment_pending,
        payment_confirmed=payment_confirmed,
        payment_expired=payment_expired,
        payment_expires_at=payment_expires_at,
        confirmation_countdown=confirmation_countdown,
        confirmation_expires_at=confirmation_expires_at,
        eta_at=eta_at,
        business_state=business_state,
    )

    can_cancel = payment_status.can_cancel(order)
    can_mock_confirm_payment = _can_mock_confirm_payment(order, is_debug=is_debug)
    actions = _build_order_actions(
        order,
        can_cancel=can_cancel,
        can_rate=_can_rate(order),
        can_mock_confirm_payment=can_mock_confirm_payment,
    )

    return TrackingData(
        order_ref=interaction.order_ref,
        status=order.status,
        display_status_key=_display_status_key(order),
        is_delivery=is_delivery,
        is_pickup=is_pickup,
        promise=promise,
        progress_steps=progress_steps,
        timeline=timeline,
        items=items,
        total_q=int(order.total_q),
        delivery_fee_q=delivery_fee_q,
        delivery_distance_km=delivery_distance_km,
        delivery_fulfillments=delivery_fulfillments,
        pickup_fulfillments=pickup_fulfillments,
        pickup=pickup,
        actions=actions,
        is_active=order.status not in TERMINAL_STATUSES,
        server_now_iso=server_now.isoformat(),
        payment_pending=payment_pending,
        payment_expired=payment_expired,
        payment_confirmed=payment_confirmed,
        show_payment_confirmed_notice=_show_payment_confirmed_notice(
            order,
            payment_confirmed=payment_confirmed,
        ),
        payment_status_key=payment_status_key,
        payment_expires_at=payment_expires_at,
        confirmation_countdown=confirmation_countdown,
        confirmation_expires_at=confirmation_expires_at,
        eta_at=eta_at,
        whatsapp_url=whatsapp_url,
        support_url=support_url,
        shop_name=shop_name,
        is_debug=is_debug,
        last_updated_iso=server_now.isoformat(),
    )


def build_tracking_status(order) -> TrackingStatusData:
    """Build the polling data projection for tracking status partials."""
    return TrackingStatusData(
        order_ref=order.ref,
        status=order.status,
        display_status_key=_display_status_key(order),
        progress_steps=_build_progress_steps(order),
        timeline=_build_timeline(order),
        is_terminal=order.status in TERMINAL_STATUSES,
    )


# ──────────────────────────────────────────────────────────────────────
# Status semantics
# ──────────────────────────────────────────────────────────────────────


def _display_status_key(order) -> str:
    """Resolve the semantic status descriptor the customer sees.

    Returns a key that Presentation maps to a label + colour. Falls back to the
    raw ``order.status`` for the plain cases.
    """
    order_data = order.data or {}
    fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
    is_delivery = fulfillment_type == "delivery"
    is_pickup = fulfillment_type == "pickup"
    payment = order_data.get("payment") or {}
    method = str(payment.get("method") or "").lower()
    has_intent = bool(payment.get("intent_ref") or payment.get("status"))
    live_payment_status = (payment_status.get_payment_status(order) or "").lower()
    payment_captured = payment_status.has_sufficient_captured_payment(order)

    if _is_payment_timeout_cancelled(order):
        return "payment_expired"
    if order.status == "new" and method in {"pix", "card"}:
        if payment_captured or live_payment_status == "authorized" or not has_intent:
            return "waiting_store_confirmation"
        return "payment_pending"
    if method == "card" and live_payment_status == "authorized" and order.status in {"new", "confirmed"}:
        return "card_authorized"
    if order.status == "confirmed" and method in {"pix", "card"} and not payment_captured and live_payment_status != "authorized":
        return "payment_pending"
    if order.status == "new":
        return "waiting_store_confirmation"
    if order.status == "ready":
        if is_delivery:
            return "ready_delivery"
        if is_pickup:
            return "ready_pickup"
    if order.status == "completed":
        return "delivered" if is_delivery else "completed"
    return order.status


def _payment_info(order) -> tuple[bool, bool, str | None, str | None]:
    """Return (pending, confirmed, status_key, expires_at_iso).

    ``status_key`` is a semantic payment descriptor (Presentation labels it),
    not a rendered string.
    """
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return False, False, None, None

    if _is_payment_timeout_cancelled(order):
        return False, False, "payment_expired", payment.get("expires_at") or None

    status = (payment_status.get_payment_status(order) or "").lower()
    if payment_status.has_sufficient_captured_payment(order):
        return False, True, "payment_confirmed", payment.get("expires_at") or None
    if status == "authorized" and method == "card":
        return False, False, "card_authorized", payment.get("expires_at") or None
    if not (payment.get("intent_ref") or payment.get("status")) and order.status == "new":
        return False, False, None, None
    if order.status not in {"new", "confirmed"}:
        return False, False, None, None
    return True, False, "payment_pending", payment.get("expires_at") or None


def _can_mock_confirm_payment(order, *, is_debug: bool) -> bool:
    if not is_debug:
        return False
    if order.status not in {"new", "confirmed"}:
        return False
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"} or not payment.get("intent_ref"):
        return False
    status = (payment_status.get_payment_status(order) or "").lower()
    return status not in {"", "unknown", "captured", "paid", "refunded", "cancelled", "failed"}


def _rating_data(order) -> dict:
    data = order.data if isinstance(order.data, dict) else {}
    rating = data.get("customer_rating")
    return rating if isinstance(rating, dict) else {}


def _can_rate(order) -> bool:
    if order.status not in {"delivered", "completed"}:
        return False
    return not bool(_rating_data(order).get("rating"))


# ──────────────────────────────────────────────────────────────────────
# Actions (Action.label resolved from config — orchestrator owns copy)
# ──────────────────────────────────────────────────────────────────────


def _copy_title(key: str, fallback: str) -> str:
    try:
        entry = resolve_copy(key, moment="*", audience="*")
        return entry.title or fallback
    except Exception:
        logger.debug("order_tracking_copy_failed key=%s", key, exc_info=True)
        return fallback


def _copy_message(key: str, fallback: str) -> str:
    try:
        entry = resolve_copy(key, moment="*", audience="*")
        return entry.message or fallback
    except Exception:
        logger.debug("order_tracking_copy_failed key=%s", key, exc_info=True)
        return fallback


def _action(
    *,
    ref: str,
    kind: str,
    label: str,
    priority: str = "primary",
    href: str = "",
    enabled: bool = True,
    reason: str = "",
    method: str = "",
    payload_schema: dict | None = None,
    idempotency: str = "none",
    confirmation: dict | None = None,
) -> Action:
    return Action(
        ref=ref,
        kind=kind,
        label=label,
        priority=priority,
        enabled=enabled,
        reason=reason,
        href=href,
        method=method,
        payload_schema=payload_schema or {},
        idempotency=idempotency,
        confirmation=confirmation or {},
    )


def _reorder_action(order, *, priority: str = "secondary") -> Action:
    return _action(
        ref="reorder",
        kind="mutation",
        label=_copy_title("TRACKING_REORDER_CTA", "Repetir pedido"),
        priority=priority,
        href=f"/api/v1/orders/{order.ref}/reorder/",
        method="POST",
        payload_schema={
            "type": "object",
            "properties": {
                "mode": {"type": "string", "enum": ["append", "replace"]},
                "idempotency_key": {"type": "string"},
            },
        },
        idempotency="required",
    )


def _build_order_actions(
    order,
    *,
    can_cancel: bool,
    can_rate: bool,
    can_mock_confirm_payment: bool,
) -> tuple[Action, ...]:
    actions: list[Action] = []
    if can_cancel:
        actions.append(_action(
            ref="cancel_order",
            kind="mutation",
            label=_copy_title("TRACKING_ACTION_CANCEL_ORDER", "Cancelar pedido"),
            priority="danger",
            href=f"/api/v1/orders/{order.ref}/cancel/",
            method="POST",
            payload_schema={
                "type": "object",
                "required": ["idempotency_key"],
                "properties": {
                    "idempotency_key": {"type": "string"},
                },
            },
            idempotency="required",
            confirmation={
                "title": _copy_title("TRACKING_CANCEL_CONFIRM_TITLE", "Cancelar pedido"),
                "warning_title": _copy_title(
                    "TRACKING_CANCEL_WARNING_TITLE",
                    "Essa ação altera o pedido em andamento",
                ),
                "warning_message": _copy_message(
                    "TRACKING_CANCEL_WARNING_MESSAGE",
                    "O cancelamento só é permitido enquanto o pagamento não foi capturado e a loja ainda permite reversão.",
                ),
                "message": _copy_message(
                    "TRACKING_CANCEL_CONFIRM_MESSAGE",
                    "Confirme apenas se não quiser mais seguir com este pedido.",
                ),
                "ack_label": _copy_title(
                    "TRACKING_CANCEL_ACK_LABEL",
                    "Entendo que o pedido será cancelado e deixará de ser preparado.",
                ),
                "cancel_label": _copy_title("TRACKING_CANCEL_KEEP_CTA", "Manter pedido"),
                "confirm_label": _copy_title("TRACKING_CANCEL_CONFIRM_CTA", "Confirmar cancelamento"),
                "severity": "danger",
            },
        ))
    if can_rate:
        actions.append(_action(
            ref="rate_order",
            kind="mutation",
            label=_copy_title("TRACKING_ACTION_RATE_ORDER", "Avaliar pedido"),
            priority="secondary",
            href=f"/api/v1/orders/{order.ref}/rate/",
            method="POST",
            payload_schema={
                "type": "object",
                "required": ["rating", "idempotency_key"],
                "properties": {
                    "rating": {"type": "integer", "minimum": 1, "maximum": 5},
                    "comment": {"type": "string", "maxLength": 500},
                    "idempotency_key": {"type": "string"},
                },
            },
            idempotency="required",
        ))
    if can_mock_confirm_payment:
        actions.append(_action(
            ref="mock_confirm_payment",
            kind="mutation",
            label=_copy_title("TRACKING_ACTION_MOCK_CONFIRM_PAYMENT", "Capturar pagamento teste"),
            priority="quiet",
            href=f"/api/v1/payment/{order.ref}/mock-confirm/",
            method="POST",
            payload_schema={
                "type": "object",
                "properties": {
                    "idempotency_key": {"type": "string"},
                },
            },
            idempotency="recommended",
        ))
    if order.status in TERMINAL_STATUSES:
        actions.append(_reorder_action(order))
    return tuple(actions)


# ──────────────────────────────────────────────────────────────────────
# Promise state machine (policy → data; copy resolved in Presentation)
# ──────────────────────────────────────────────────────────────────────


def _promise(
    *,
    state: str,
    tone: str,
    deadline_at: str | None = None,
    deadline_kind: str | None = None,
    timer_mode: str = "none",
    deadline_action: str = "none",
    requires_active_notification: bool = False,
    notification_topic: str | None = None,
    actions: tuple[Action, ...] = (),
    eta_at: str | None = None,
    next_opening_phrase: str = "",
) -> TrackingPromiseData:
    return TrackingPromiseData(
        state=state,
        tone=tone,
        deadline_at=deadline_at,
        deadline_kind=deadline_kind,
        timer_mode=timer_mode,
        deadline_action=deadline_action,
        requires_active_notification=requires_active_notification,
        notification_topic=notification_topic,
        actions=actions,
        eta_at=eta_at,
        next_opening_phrase=next_opening_phrase,
    )


def _build_promise(
    order,
    *,
    is_delivery: bool,
    payment_pending: bool,
    payment_confirmed: bool,
    payment_expired: bool,
    payment_expires_at: str | None,
    confirmation_countdown: bool,
    confirmation_expires_at: str | None,
    eta_at: str | None,
    business_state: BusinessCalendarState,
) -> TrackingPromiseData:
    if payment_expired:
        return _promise(
            state="payment_expired",
            tone="danger",
            deadline_kind="payment",
            requires_active_notification=True,
            notification_topic="payment_expired",
        )

    if payment_pending:
        state = "payment_requested" if order.status == "confirmed" else "payment_pending"
        return _promise(
            state=state,
            tone="warning",
            deadline_at=payment_expires_at,
            deadline_kind="payment",
            timer_mode="countdown" if payment_expires_at else "none",
            deadline_action="show_payment_expired",
            requires_active_notification=state == "payment_requested",
            notification_topic="payment_requested" if state == "payment_requested" else None,
            actions=(
                _action(
                    ref="pay_now",
                    kind="link",
                    label=_copy_title("TRACKING_PAYMENT_CTA", "Pagar agora"),
                    href=f"/pedido/{order.ref}/pagamento/",
                ),
            ),
        )

    if _store_confirmation_is_deferred(order, payment_pending=payment_pending, business_state=business_state):
        next_opening_phrase = format_next_opening(
            business_state.next_open_at,
            now=business_state.resolved_at,
        )
        return _promise(
            state="availability_deferred",
            tone="info",
            next_opening_phrase=next_opening_phrase or "",
        )

    payment_method = str(((order.data or {}).get("payment") or {}).get("method") or "").lower()
    live_payment_status = (payment_status.get_payment_status(order) or "").lower()
    card_authorized = payment_method == "card" and live_payment_status == "authorized"
    if card_authorized and order.status in {"new", "confirmed"}:
        return _promise(state="card_authorized", tone="info")

    if confirmation_countdown:
        return _promise(
            state="availability_check",
            tone="info",
            deadline_at=confirmation_expires_at,
            deadline_kind="availability",
            timer_mode="countdown" if confirmation_expires_at else "none",
            deadline_action="refresh_tracking",
        )

    if payment_confirmed and order.status in {"new", "confirmed"}:
        return _promise(state="payment_confirmed", tone="success")

    if order.status == "preparing":
        return _promise(state="preparing", tone="info", eta_at=eta_at)

    if order.status == "ready":
        if is_delivery:
            return _promise(
                state="ready_delivery",
                tone="success",
                requires_active_notification=False,
            )
        return _promise(
            state="ready_pickup",
            tone="success",
            actions=(
                _action(
                    ref="pickup",
                    kind="instruction",
                    label=_copy_title("TRACKING_ACTION_READY_PICKUP", "Retirar pedido"),
                    priority="primary",
                ),
            ),
        )

    if order.status == "dispatched":
        # Trecho mais sensível: o produto saiu, com courier terceirizado, sem
        # rastreio nem detecção de chegada. Não prometemos "avisamos quando
        # chegar". Damos janela estimada + deixamos o cliente fechar o loop
        # ("Recebi") — sem depender disso (operador/auto-conclusão também fecham).
        actions: tuple[Action, ...] = ()
        if is_delivery:
            actions = (
                _action(
                    ref="confirm_received",
                    kind="mutation",
                    label=_copy_title("TRACKING_ACTION_CONFIRM_RECEIVED", "Recebi meu pedido"),
                    priority="primary",
                    href=f"/api/v1/orders/{order.ref}/confirm-received/",
                    method="POST",
                    payload_schema={
                        "type": "object",
                        "required": ["idempotency_key"],
                        "properties": {"idempotency_key": {"type": "string"}},
                    },
                    idempotency="required",
                ),
            )
        return _promise(
            state="dispatched",
            tone="info",
            eta_at=eta_at,
            requires_active_notification=True,
            notification_topic="order_dispatched",
            actions=actions,
        )

    terminal_tone = {
        "delivered": "success",
        "completed": "success",
        "cancelled": "danger",
    }
    if order.status in terminal_tone:
        return _promise(
            state=order.status,
            tone=terminal_tone[order.status],
            requires_active_notification=order.status == "delivered",
            notification_topic="order_delivered" if order.status == "delivered" else None,
        )

    return _promise(state="received", tone="info")


# ──────────────────────────────────────────────────────────────────────
# Timeline & progress
# ──────────────────────────────────────────────────────────────────────


def _build_timeline(order) -> tuple[TrackingTimelineEventData, ...]:
    raw: list[tuple] = []

    for event in order.events.order_by("seq"):
        payload = event.payload or {}
        label_key = payload.get("new_status", "") if event.type == "status_changed" else ""
        raw.append((event.created_at, event.type, label_key))

    for ful in order.fulfillments.all():
        if ful.dispatched_at:
            raw.append((ful.dispatched_at, "fulfillment.dispatched", "shipment_dispatched"))
        if ful.delivered_at:
            raw.append((ful.delivered_at, "fulfillment.delivered", "shipment_delivered"))

    raw.sort(key=lambda x: x[0])
    return tuple(
        TrackingTimelineEventData(
            event_type=event_type,
            at=created_at.isoformat(),
            label_key=label_key,
        )
        for created_at, event_type, label_key in raw
    )


def _build_progress_steps(
    order,
    *,
    is_delivery: bool | None = None,
    is_pickup: bool | None = None,
    payment_confirmed: bool | None = None,
) -> tuple[TrackingProgressStepData, ...]:
    """Build the customer-facing operational progress path.

    Intentionally separate from ``timeline``. Timeline is audit history; this is
    the stable path the customer uses to understand what is done, what is
    current, and what is still ahead. Step *labels* are resolved in Presentation
    from each step ``key``.
    """
    order_data = order.data or {}
    if is_delivery is None:
        fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
        is_delivery = fulfillment_type == "delivery"
    if is_pickup is None:
        fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
        is_pickup = fulfillment_type == "pickup"
    if payment_confirmed is None:
        payment_confirmed = _payment_info(order)[1]

    include_payment = _should_show_payment_step(order)
    cancelled = order.status == "cancelled"
    active_key = _active_progress_key(
        order,
        is_delivery=is_delivery,
        include_payment=include_payment,
        payment_confirmed=payment_confirmed,
    )

    specs: list[tuple[str, str | None]] = [
        ("received", _iso(order.created_at)),
        ("availability", _progress_timestamp(order, "confirmed")),
    ]
    if include_payment:
        specs.append(("payment", _payment_confirmed_timestamp(order)))
    specs.append(("preparing", _progress_timestamp(order, "preparing")))
    if is_delivery:
        specs.extend([
            ("ready_delivery", _progress_timestamp(order, "ready")),
            ("dispatched", _progress_timestamp(order, "dispatched")),
            ("delivered", _progress_timestamp(order, "delivered")),
            ("completed", _progress_timestamp(order, "completed")),
        ])
    elif is_pickup:
        specs.extend([
            ("ready", _progress_timestamp(order, "ready")),
            ("completed", _progress_timestamp(order, "completed")),
        ])
    else:
        specs.extend([
            ("ready", _progress_timestamp(order, "ready")),
            ("completed", _progress_timestamp(order, "completed")),
        ])
    if cancelled:
        specs[-1] = ("cancelled", _progress_timestamp(order, "cancelled"))

    active_index = next((idx for idx, (key, _) in enumerate(specs) if key == active_key), 0)
    steps: list[TrackingProgressStepData] = []
    for idx, (key, timestamp) in enumerate(specs):
        if key == "cancelled":
            state = "cancelled"
        elif cancelled:
            state = "completed" if _step_was_reached(order, key, payment_confirmed=payment_confirmed) else "pending"
        elif idx < active_index:
            state = "completed"
        elif idx == active_index:
            state = "current"
        else:
            state = "pending"
        steps.append(TrackingProgressStepData(key=key, state=state, at=timestamp))
    return tuple(step for step in steps if _should_render_progress_step(step))


def _should_render_progress_step(step: TrackingProgressStepData) -> bool:
    if step.state == "pending":
        return False
    if step.key == "received":
        return True
    return bool(step.at)


def _active_progress_key(
    order,
    *,
    is_delivery: bool,
    include_payment: bool,
    payment_confirmed: bool,
) -> str:
    if order.status == "cancelled":
        return "cancelled"
    if order.status == "returned":
        return "completed"
    if order.status == "new":
        return "availability" if payment_confirmed else "received"
    if order.status == "confirmed":
        if include_payment and payment_confirmed:
            return "payment"
        return "availability"
    if order.status == "preparing":
        return "preparing"
    if order.status == "ready":
        return "ready_delivery" if is_delivery else "ready"
    if order.status == "dispatched":
        return "dispatched"
    if order.status == "delivered":
        return "delivered"
    if order.status == "completed":
        return "completed"
    return "received"


def _should_show_payment_step(order) -> bool:
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method in {"pix", "card", "external"}:
        return True
    status = str(payment.get("status") or "").lower()
    return status in {"authorized", "captured", "paid"}


def _show_payment_confirmed_notice(order, *, payment_confirmed: bool) -> bool:
    """Show the standalone payment alert only before operation has moved on."""
    return payment_confirmed and order.status in {"new", "confirmed"}


def _step_was_reached(order, key: str, *, payment_confirmed: bool) -> bool:
    if key == "received":
        return True
    if key == "availability":
        return bool(_progress_timestamp(order, "confirmed"))
    if key == "payment":
        return payment_confirmed
    if key == "preparing":
        return bool(_progress_timestamp(order, "preparing"))
    if key == "ready":
        return bool(_progress_timestamp(order, "ready"))
    if key == "ready_delivery":
        return bool(_progress_timestamp(order, "ready"))
    if key == "dispatched":
        return bool(_progress_timestamp(order, "dispatched"))
    if key == "delivered":
        return bool(_progress_timestamp(order, "delivered"))
    if key == "completed":
        return bool(_progress_timestamp(order, "completed"))
    return False


def _progress_timestamp(order, status: str) -> str | None:
    field_name = f"{status}_at"
    value = getattr(order, field_name, None)
    if value:
        return _iso(value)
    if status == "confirmed":
        event = _event_for_status(order, "confirmed")
    elif status in {"preparing", "ready", "dispatched", "delivered", "completed", "cancelled"}:
        event = _event_for_status(order, status)
    else:
        event = None
    if event:
        return _iso(event.created_at)
    return None


def _event_for_status(order, status: str):
    return (
        order.events.filter(type="status_changed", payload__new_status=status)
        .order_by("created_at", "seq")
        .first()
    )


def _payment_confirmed_timestamp(order) -> str | None:
    payment = (order.data or {}).get("payment") or {}
    captured_at = _parse_datetime(payment.get("captured_at"))
    if captured_at:
        return _iso(captured_at)
    event = order.events.filter(type="payment.captured").order_by("created_at", "seq").first()
    if event:
        return _iso(event.created_at)
    intent_ref = payment.get("intent_ref")
    if intent_ref:
        try:
            from shopman.payman import PaymentService

            intent = PaymentService.get(intent_ref)
        except Exception:
            logger.debug(
                "order_tracking_payment_capture_timestamp_failed order=%s intent=%s",
                order.ref,
                intent_ref,
                exc_info=True,
            )
        else:
            if intent.captured_at:
                return _iso(intent.captured_at)
    return None


# ──────────────────────────────────────────────────────────────────────
# Items & fulfillments
# ──────────────────────────────────────────────────────────────────────


def _build_items(order) -> tuple[TrackingItemData, ...]:
    return tuple(
        TrackingItemData(
            sku=item.sku,
            name=item.name or item.sku,
            qty=int(item.qty),
            unit_price_q=int(item.unit_price_q),
            line_total_q=int(item.line_total_q),
        )
        for item in order.items.all()
    )


def _carrier_tracking_url(carrier: str, tracking_code: str) -> str | None:
    if not carrier or not tracking_code:
        return None
    template = CARRIER_TRACKING_URLS.get(carrier.lower())
    if template:
        return template.format(code=tracking_code)
    return None


def _build_fulfillments(
    order,
    *,
    is_delivery: bool | None = None,
    is_pickup: bool | None = None,
) -> tuple[tuple[TrackingFulfillmentData, ...], tuple[TrackingFulfillmentData, ...]]:
    delivery: list[TrackingFulfillmentData] = []
    pickup: list[TrackingFulfillmentData] = []
    if is_delivery is None:
        order_data = order.data or {}
        fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
        is_delivery = fulfillment_type == "delivery"
    if is_pickup is None:
        order_data = order.data or {}
        fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
        is_pickup = fulfillment_type == "pickup"

    for ful in order.fulfillments.all():
        tracking_url = ful.tracking_url or _carrier_tracking_url(ful.carrier, ful.tracking_code)
        projected = TrackingFulfillmentData(
            status=ful.status,
            tracking_code=ful.tracking_code or None,
            tracking_url=tracking_url,
            carrier=ful.carrier or None,
            dispatched_at=_iso(ful.dispatched_at) if ful.dispatched_at else None,
            delivered_at=_iso(ful.delivered_at) if ful.delivered_at else None,
        )
        if is_delivery or ful.carrier or ful.tracking_code:
            delivery.append(projected)
        elif is_pickup:
            pickup.append(projected)

    return tuple(delivery), tuple(pickup)


# ──────────────────────────────────────────────────────────────────────
# Pickup point
# ──────────────────────────────────────────────────────────────────────


def _pickup_data() -> TrackingPickupData | None:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        if not shop:
            return None

        directions_url = _pickup_directions_url(shop)
        address = _pickup_display_address(shop)
        opening_hours = dict(shop.opening_hours or {})
        if not (address or opening_hours or directions_url):
            return None
        return TrackingPickupData(
            address=address,
            directions_url=directions_url,
            opening_hours=opening_hours,
        )
    except Exception:
        logger.warning("order_tracking_pickup_info_failed", exc_info=True)
        return None


def _pickup_directions_url(shop) -> str | None:
    from urllib.parse import urlencode

    destination = ""
    route_address = _pickup_route_address(shop)
    if route_address:
        destination = route_address
    elif shop.latitude and shop.longitude:
        destination = f"{shop.latitude},{shop.longitude}"
    if not destination:
        return None

    params = {"api": "1", "destination": destination}
    if shop.place_id:
        params["destination_place_id"] = shop.place_id
    return f"https://www.google.com/maps/dir/?{urlencode(params)}"


def _pickup_display_address(shop) -> str:
    formatted = str(getattr(shop, "formatted_address", "") or "").strip()
    if formatted:
        return formatted
    if not _shop_has_specific_address(shop):
        return ""
    return str(getattr(shop, "full_address", "") or "").strip()


def _pickup_route_address(shop) -> str:
    formatted = str(getattr(shop, "formatted_address", "") or "").strip()
    if formatted:
        return formatted
    if not _shop_has_specific_address(shop):
        return ""
    return _pickup_display_address(shop).replace("\n", ", ")


def _shop_has_specific_address(shop) -> bool:
    return any(
        str(getattr(shop, field_name, "") or "").strip()
        for field_name in ("route", "street_number", "neighborhood", "postal_code")
    )


# ──────────────────────────────────────────────────────────────────────
# Confirmation, ETA, contact
# ──────────────────────────────────────────────────────────────────────


def _confirmation_info(
    order,
    *,
    payment_pending: bool,
    business_state: BusinessCalendarState | None = None,
) -> tuple[bool, str | None]:
    if order.status != "new":
        return False, None
    if payment_pending:
        return False, None
    if business_state is not None and business_state.is_closed:
        return False, None
    try:
        from shopman.shop.config import ChannelConfig

        cfg = ChannelConfig.for_channel(order.channel_ref).confirmation
        if cfg.mode == "auto_confirm":
            expires_at = _confirmation_deadline(order)
            if not expires_at:
                return False, None
            if expires_at <= timezone.now():
                return False, None
            return True, expires_at.isoformat()
    except Exception:
        logger.warning("order_tracking_confirmation_failed order=%s", order.ref, exc_info=True)
    return False, None


def _store_confirmation_is_deferred(
    order,
    *,
    payment_pending: bool,
    business_state: BusinessCalendarState,
) -> bool:
    if order.status != "new":
        return False
    if payment_pending:
        return False
    return business_state.is_closed


def _confirmation_deadline(order) -> datetime | None:
    directive = (
        Directive.objects.filter(
            topic="confirmation.timeout",
            payload__order_ref=order.ref,
            payload__action="confirm",
            status="queued",
        )
        .order_by("available_at", "id")
        .first()
    )
    if not directive:
        return None
    if directive.available_at:
        return directive.available_at
    return _parse_datetime((directive.payload or {}).get("expires_at"))


def _eta_at(order) -> str | None:
    """ETA ISO for the two windows the customer cares about:

    - ``preparing`` → quando o pedido fica pronto (prep_time).
    - ``dispatched`` + delivery → janela estimada de CHEGADA (saída + tempo médio
      de entrega). Couriers são terceirizados/sem rastreio, então é uma estimativa
      honesta por configuração, não um horário rastreado.
    """
    try:
        from shopman.shop.models import Shop
        from shopman.shop.services.order_helpers import delivery_eta_minutes

        shop = Shop.load()
        round_to_5 = False
        if order.status == "preparing":
            minutes = getattr(shop, "prep_time_minutes", None) or 30
            baseline = getattr(order, "preparing_at", None)
            if baseline is None:
                event = _event_for_status(order, "preparing")
                baseline = event.created_at if event else None
        elif order.status == "dispatched":
            data = order.data or {}
            if (data.get("fulfillment_type") or data.get("delivery_method", "")) != "delivery":
                return None
            minutes = delivery_eta_minutes(shop, data)
            round_to_5 = True
            event = _event_for_status(order, "dispatched")
            baseline = event.created_at if event else None
        else:
            return None
        if baseline is None:
            return None
        eta = baseline + timezone.timedelta(minutes=int(round(minutes)))
        if round_to_5:
            # Tempo "redondo" e levemente conservador: arredonda PARA CIMA ao
            # próximo múltiplo de 5 (um respiro a mais na promessa).
            eta = eta.replace(second=0, microsecond=0)
            remainder = eta.minute % 5
            if remainder:
                eta += timezone.timedelta(minutes=5 - remainder)
        return eta.isoformat()
    except Exception:
        logger.debug("order_tracking_eta_failed order=%s", order.ref, exc_info=True)
        return None


def _contact_and_share(order) -> tuple[str, str, str]:
    """Return (whatsapp_url, support_base_url, shop_name) as data.

    Presentation appends the localized support message to the base URL and
    builds the share text from ``shop_name`` + order ref.
    """
    whatsapp_url = ""
    shop_name = "loja"
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        if shop:
            shop_name = shop.name or "loja"
            for link in shop.social_links or []:
                if "wa.me" in link or "whatsapp.com" in link:
                    whatsapp_url = link
                    break
            if not whatsapp_url and shop.phone:
                digits = "".join(char for char in shop.phone if char.isdigit())
                whatsapp_url = f"https://wa.me/{digits}"
    except Exception:
        logger.warning("order_tracking_contact_failed order=%s", order.ref, exc_info=True)

    return whatsapp_url, whatsapp_url, shop_name


# ──────────────────────────────────────────────────────────────────────
# Small helpers
# ──────────────────────────────────────────────────────────────────────


def _iso(value) -> str | None:
    try:
        return value.isoformat()
    except Exception:
        logger.debug("order_tracking._iso degraded for value=%r", value, exc_info=True)
        return None


def _parse_datetime(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        dt = parse_datetime(str(value))
        if dt is None:
            try:
                dt = datetime.fromisoformat(str(value))
            except ValueError:
                return None
    if not timezone.is_aware(dt):
        return timezone.make_aware(dt)
    return dt


def _is_payment_timeout_cancelled(order) -> bool:
    if order.status != "cancelled":
        return False
    data = order.data or {}
    return data.get("cancellation_reason") == "payment_timeout" or bool(data.get("payment_timeout_at"))


__all__ = [
    "TrackingData",
    "TrackingFulfillmentData",
    "TrackingItemData",
    "TrackingPickupData",
    "TrackingProgressStepData",
    "TrackingPromiseData",
    "TrackingStatusData",
    "TrackingTimelineEventData",
    "build_tracking",
    "build_tracking_status",
]
