"""Canonical order tracking projections for customer-facing surfaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlencode

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from shopman.orderman.models import Directive
from shopman.utils.monetary import format_money

from shopman.shop.omotenashi import resolve_copy
from shopman.shop.projections.types import (
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    FulfillmentProjection,
    OrderItemProjection,
    OrderProgressStepProjection,
    SurfaceActionProjection,
    TimelineEventProjection,
)
from shopman.shop.services import payment_status
from shopman.shop.services.business_calendar import (
    BusinessCalendarState,
    current_business_state,
    format_next_opening,
)
from shopman.shop.services.interaction_context import InteractionContext

logger = logging.getLogger(__name__)

CARRIER_TRACKING_URLS: dict[str, str] = {
    "correios": "https://rastreamento.correios.com.br/?objetos={code}",
    "jadlog": "https://www.jadlog.com.br/tracking?code={code}",
}

TERMINAL_STATUSES = frozenset({"completed", "cancelled", "returned"})

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
    """Surface chrome copy for the tracking projection."""

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
    """Current operational promise shown to the customer.

    This normalizes the active timer/deadline for the tracking page. Order,
    payment and directive state remain the source of truth; the UI consumes this
    projection instead of recomputing timeout semantics in templates.
    """

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
    actions: tuple[SurfaceActionProjection, ...] = ()
    next_event: str = ""
    recovery: str = ""
    active_notification: str = ""


@dataclass(frozen=True)
class OrderTrackingPromiseRowProjection:
    """Customer-facing promise detail row resolved by the canonical backend."""

    label: str
    value: str
    url: str | None = None


@dataclass(frozen=True)
class OrderTrackingProjection:
    """Canonical full tracking projection."""

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
    actions: tuple[SurfaceActionProjection, ...]
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
    """Canonical polling projection for tracking status partials."""

    order_ref: str
    status: str
    status_label: str
    status_color: str
    progress_steps: tuple[OrderProgressStepProjection, ...]
    timeline: tuple[TimelineEventProjection, ...]
    is_terminal: bool


def build_tracking(order, *, is_debug: bool = False) -> OrderTrackingProjection:
    """Build the full tracking projection for an order."""
    interaction = InteractionContext.from_order(order, surface_ref="tracking")
    server_now = timezone.now()
    payment_expired = _is_payment_timeout_cancelled(order)
    status_label, status_color = _status_display(order)
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
    pickup_info = _pickup_info() if is_pickup else None

    delivery_fee_q = order_data.get("delivery_fee_q")
    delivery_fee_display: str | None = None
    if delivery_fee_q is not None:
        delivery_fee_display = "Grátis" if delivery_fee_q == 0 else f"R$ {format_money(delivery_fee_q)}"

    payment_pending, payment_confirmed, payment_status_label, payment_expires_at = _payment_info(order)
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
    whatsapp_url, support_url, share_text = _contact_and_share(order)
    eta_display = _eta_display(order)
    promise = _build_promise(
        order,
        is_delivery=is_delivery,
        payment_pending=payment_pending,
        payment_confirmed=payment_confirmed,
        payment_expired=payment_expired,
        payment_expires_at=payment_expires_at,
        confirmation_countdown=confirmation_countdown,
        confirmation_expires_at=confirmation_expires_at,
        eta_display=eta_display,
        business_state=business_state,
    )
    last_updated_display = _copy_title("TRACKING_PROMISE_UPDATED_NOW", "Atualizado agora")

    can_cancel = payment_status.can_cancel(order)
    can_mock_confirm_payment = _can_mock_confirm_payment(order, is_debug=is_debug)
    actions = _build_order_actions(
        order,
        can_cancel=can_cancel,
        can_rate=_can_rate(order),
        can_mock_confirm_payment=can_mock_confirm_payment,
    )

    return OrderTrackingProjection(
        order_ref=interaction.order_ref,
        status=order.status,
        status_label=status_label,
        status_color=status_color,
        copy=_tracking_copy(),
        promise=promise,
        promise_rows=_build_promise_rows(promise, last_updated_display=last_updated_display),
        promise_deadline_label=_clean_label(_copy_title("TRACKING_PROMISE_LABEL_DEADLINE", "Prazo")),
        progress_steps=progress_steps,
        timeline=timeline,
        items=items,
        total_display=f"R$ {format_money(order.total_q)}",
        delivery_fee_display=delivery_fee_display,
        is_delivery=is_delivery,
        delivery_fulfillments=delivery_fulfillments,
        pickup_fulfillments=pickup_fulfillments,
        pickup_info=pickup_info,
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
        payment_status_label=payment_status_label,
        payment_expires_at=payment_expires_at,
        confirmation_countdown=confirmation_countdown,
        confirmation_expires_at=confirmation_expires_at,
        eta_display=eta_display,
        whatsapp_url=whatsapp_url,
        support_url=support_url,
        share_text=share_text,
        is_debug=is_debug,
        last_updated_iso=server_now.isoformat(),
        last_updated_display=last_updated_display,
        stale_after_seconds=45,
    )


def build_tracking_status(order) -> OrderTrackingStatusProjection:
    """Build the polling projection for tracking status partials."""
    status_label, status_color = _status_display(order)
    return OrderTrackingStatusProjection(
        order_ref=order.ref,
        status=order.status,
        status_label=status_label,
        status_color=status_color,
        progress_steps=_build_progress_steps(order),
        timeline=_build_timeline(order),
        is_terminal=order.status in TERMINAL_STATUSES,
    )


def _carrier_tracking_url(carrier: str, tracking_code: str) -> str | None:
    if not carrier or not tracking_code:
        return None
    template = CARRIER_TRACKING_URLS.get(carrier.lower())
    if template:
        return template.format(code=tracking_code)
    return None


def _status_display(order) -> tuple[str, str]:
    order_data = order.data or {}
    fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
    is_delivery = fulfillment_type == "delivery"
    is_pickup = fulfillment_type == "pickup"
    payment = order_data.get("payment") or {}
    method = str(payment.get("method") or "").lower()
    has_intent = bool(payment.get("intent_ref") or payment.get("status"))
    live_payment_status = (payment_status.get_payment_status(order) or "").lower()
    payment_captured = payment_status.has_sufficient_captured_payment(order)

    label = ORDER_STATUS_LABELS_PT.get(order.status, order.status)
    if _is_payment_timeout_cancelled(order):
        label = _copy_title("TRACKING_STATUS_PAYMENT_EXPIRED", "Pagamento expirado")
    elif order.status == "new" and method in {"pix", "card"}:
        if payment_captured or live_payment_status == "authorized" or not has_intent:
            label = _copy_title(
                "TRACKING_STATUS_WAITING_STORE_CONFIRMATION",
                "Aguardando confirmação",
            )
        else:
            label = _copy_title("TRACKING_STATUS_PAYMENT_PENDING", "Aguardando pagamento")
    elif method == "card" and live_payment_status == "authorized" and order.status in {"new", "confirmed"}:
        label = "Pagamento autorizado"
    elif order.status == "confirmed" and method in {"pix", "card"} and not payment_captured and live_payment_status != "authorized":
        label = _copy_title("TRACKING_STATUS_PAYMENT_PENDING", "Aguardando pagamento")
    elif order.status == "new":
        label = _copy_title(
            "TRACKING_STATUS_WAITING_STORE_CONFIRMATION",
            "Aguardando confirmação",
        )
    elif order.status == "ready":
        if is_delivery:
            label = "Aguardando entregador"
        elif is_pickup:
            label = "Pronto para retirada"
    elif order.status == "completed":
        label = "Entregue" if is_delivery else "Concluído"

    color = ORDER_STATUS_COLORS.get(order.status, "bg-surface-alt text-on-surface/60 border border-outline")
    return label, color


def _payment_info(order) -> tuple[bool, bool, str | None, str | None]:
    payment = (order.data or {}).get("payment") or {}
    method = str(payment.get("method") or "").lower()
    if method not in {"pix", "card"}:
        return False, False, None, None

    if _is_payment_timeout_cancelled(order):
        return False, False, "Prazo para pagamento expirado", payment.get("expires_at") or None

    status = (payment_status.get_payment_status(order) or "").lower()
    if payment_status.has_sufficient_captured_payment(order):
        return False, True, "Pagamento confirmado", payment.get("expires_at") or None
    if status == "authorized" and method == "card":
        return False, False, "Pagamento autorizado", payment.get("expires_at") or None
    if not (payment.get("intent_ref") or payment.get("status")) and order.status == "new":
        return False, False, None, None
    if order.status not in {"new", "confirmed"}:
        return False, False, None, None
    return True, False, "Aguardando confirmação do pagamento", payment.get("expires_at") or None


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


def _clean_label(value: str) -> str:
    return str(value or "").strip().rstrip(":").strip()


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
) -> SurfaceActionProjection:
    return SurfaceActionProjection(
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


def _reorder_action(order, *, priority: str = "secondary") -> SurfaceActionProjection:
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
) -> tuple[SurfaceActionProjection, ...]:
    actions: list[SurfaceActionProjection] = []
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


def _first_visible_action(actions: tuple[SurfaceActionProjection, ...]) -> SurfaceActionProjection | None:
    for action in actions:
        if action.enabled:
            return action
    return actions[0] if actions else None


def _build_promise_rows(
    promise: OrderTrackingPromiseProjection,
    *,
    last_updated_display: str,
) -> tuple[OrderTrackingPromiseRowProjection, ...]:
    rows: list[OrderTrackingPromiseRowProjection] = []
    if promise.next_event:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(_copy_title("TRACKING_PROMISE_LABEL_NEXT", "Próximo passo")),
            value=promise.next_event,
        ))
    visible_action = _first_visible_action(promise.actions)
    if visible_action:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(_copy_title("TRACKING_PROMISE_LABEL_ACTION", "Sua ação")),
            value=visible_action.label,
            url=visible_action.href or None,
        ))
    if promise.recovery:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(_copy_title("TRACKING_PROMISE_LABEL_RECOVERY", "Se algo mudar")),
            value=promise.recovery,
        ))
    if promise.requires_active_notification and promise.active_notification:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(_copy_title("TRACKING_PROMISE_LABEL_ACTIVE_NOTIFICATION", "Aviso")),
            value=promise.active_notification,
        ))
    if last_updated_display:
        rows.append(OrderTrackingPromiseRowProjection(
            label=_clean_label(_copy_title("TRACKING_PROMISE_LABEL_UPDATED", "Última atualização")),
            value=last_updated_display,
        ))
    return tuple(rows)


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
    eta_display: str | None,
    business_state: BusinessCalendarState,
) -> OrderTrackingPromiseProjection:
    if payment_expired:
        title, message = _copy_pair(
            "TRACKING_PAYMENT_EXPIRED",
            "O prazo para pagamento expirou.",
            "O pedido foi automaticamente cancelado.",
        )
        return OrderTrackingPromiseProjection(
            state="payment_expired",
            title=title,
            message=message,
            tone="danger",
            deadline_at=None,
            deadline_kind="payment",
            timer_mode="none",
            deadline_action="none",
            requires_active_notification=True,
            notification_topic="payment_expired",
            actions=(),
            next_event="",
            recovery="",
        )

    if payment_pending:
        if order.status == "confirmed":
            title, message = _copy_pair(
                "TRACKING_PAYMENT_REQUESTED",
                "Disponibilidade confirmada.",
                "Para continuar, conclua o pagamento.",
            )
            state = "payment_requested"
        else:
            title, message = _copy_pair(
                "TRACKING_PAYMENT_PENDING",
                "Recebemos seu pedido.",
                "Aguardamos a confirmação do pagamento.",
            )
            state = "payment_pending"
        return OrderTrackingPromiseProjection(
            state=state,
            title=title,
            message=message,
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
            next_event=_copy_message("TRACKING_PROMISE_PAYMENT_NEXT", "Depois do pagamento, seguimos com o pedido."),
            recovery=_copy_message(
                "TRACKING_PROMISE_PAYMENT_RECOVERY",
                "Se o prazo expirar, o pedido será cancelado automaticamente e o estoque reservado será liberado.",
            ),
            active_notification=(
                _copy_message(
                    "TRACKING_PROMISE_PAYMENT_ACTIVE_NOTIFICATION",
                    "Também avisamos por um canal ativo habilitado, porque o PIX depende da sua ação.",
                )
                if state == "payment_requested"
                else ""
            ),
        )

    if _store_confirmation_is_deferred(order, payment_pending=payment_pending, business_state=business_state):
        next_opening = format_next_opening(
            business_state.next_open_at,
            now=business_state.resolved_at,
        )
        return OrderTrackingPromiseProjection(
            state="availability_deferred",
            title=_copy_title("TRACKING_STEP_RECEIVED", "Recebemos seu pedido."),
            message=_copy_message(
                "TRACKING_PROMISE_CLOSED_HOURS_MESSAGE",
                "Estamos fechados agora. Vamos conferir a disponibilidade quando abrirmos.",
            ),
            tone="info",
            deadline_at=None,
            deadline_kind=None,
            timer_mode="none",
            deadline_action="none",
            requires_active_notification=False,
            notification_topic=None,
            actions=(),
            next_event=(
                _copy_message("TRACKING_PROMISE_CLOSED_HOURS_NEXT_PREFIX", "Próxima abertura:")
                + f" {next_opening}."
                if next_opening
                else _copy_message(
                    "TRACKING_PROMISE_CLOSED_HOURS_NEXT_UNKNOWN",
                    "Atualizaremos o pedido assim que o próximo expediente estiver definido.",
                )
            ),
        )

    payment_method = str(((order.data or {}).get("payment") or {}).get("method") or "").lower()
    live_payment_status = (payment_status.get_payment_status(order) or "").lower()
    card_authorized = payment_method == "card" and live_payment_status == "authorized"
    if card_authorized and order.status in {"new", "confirmed"}:
        return OrderTrackingPromiseProjection(
            state="card_authorized",
            title=_copy_title("TRACKING_CARD_AUTHORIZED", "Pagamento autorizado."),
            message=_copy_message("TRACKING_CARD_AUTHORIZED", "Você não precisa fazer nada agora."),
            tone="info",
            deadline_at=None,
            deadline_kind=None,
            timer_mode="none",
            deadline_action="none",
            requires_active_notification=False,
            notification_topic=None,
            actions=(),
            next_event=(
                _copy_message("TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_NEW", "O estabelecimento vai conferir a disponibilidade.")
                if order.status == "new"
                else _copy_message(
                    "TRACKING_PROMISE_CARD_AUTHORIZED_NEXT_CONFIRMED",
                    "Assim que a confirmação financeira terminar, seguimos com o pedido.",
                )
            ),
        )

    if confirmation_countdown:
        return OrderTrackingPromiseProjection(
            state="availability_check",
            title=_copy_title("TRACKING_STEP_RECEIVED", "Recebemos seu pedido."),
            message="",
            tone="info",
            deadline_at=confirmation_expires_at,
            deadline_kind="availability",
            timer_mode="countdown" if confirmation_expires_at else "none",
            deadline_action="refresh_tracking",
            requires_active_notification=False,
            notification_topic=None,
            actions=(),
            next_event="",
            recovery=_copy_message(
                "TRACKING_PROMISE_AVAILABILITY_RECOVERY",
                "Se o estabelecimento não confirmar a tempo, atualizaremos o pedido aqui.",
            ),
        )

    if payment_confirmed and order.status in {"new", "confirmed"}:
        return OrderTrackingPromiseProjection(
            state="payment_confirmed",
            title=_copy_title("TRACKING_STEP_PAYMENT_CONFIRMED", "Reconhecemos o pagamento."),
            message=_copy_message("TRACKING_PROMISE_PAYMENT_CONFIRMED_MESSAGE", "Nenhuma ação necessária agora."),
            tone="success",
            deadline_at=None,
            deadline_kind=None,
            timer_mode="none",
            deadline_action="none",
            requires_active_notification=False,
            notification_topic=None,
            actions=(),
            next_event=(
                _copy_message(
                    "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_NEW",
                    "O estabelecimento está conferindo a disponibilidade.",
                )
                if order.status == "new"
                else _copy_message(
                    "TRACKING_PROMISE_PAYMENT_CONFIRMED_NEXT_CONFIRMED",
                    "Vamos começar o preparo do seu pedido.",
                )
            ),
        )

    if order.status == "preparing":
        title = _copy_title("TRACKING_STEP_PREPARING", "Estamos preparando seu pedido.")
        message = f"Previsão para ficar pronto às {eta_display}." if eta_display else ""
        return OrderTrackingPromiseProjection(
            state="preparing",
            title=title,
            message=message,
            tone="info",
            deadline_at=None,
            deadline_kind=None,
            timer_mode="none",
            deadline_action="none",
            requires_active_notification=False,
            notification_topic=None,
            actions=(),
            next_event=(
                _copy_message("TRACKING_PROMISE_PREPARING_NEXT_PICKUP", "Quando estiver pronto, avisaremos você.")
                if not is_delivery
                else _copy_message(
                    "TRACKING_PROMISE_PREPARING_NEXT_DELIVERY",
                    "Quando estiver pronto, solicitaremos a coleta para entrega.",
                )
            ),
        )

    if order.status == "ready":
        if is_delivery:
            title, message = _copy_pair(
                "TRACKING_DELIVERY_WAITING_COURIER",
                "Aguardando entregador.",
                "Já solicitamos a coleta do seu pedido. Assim que sair para entrega avisamos.",
            )
            state = "ready_delivery"
        else:
            title = _copy_title("TRACKING_STEP_READY_PICKUP", "Seu pedido está pronto para retirada.")
            message = ""
            state = "ready_pickup"
        ready_actions = ()
        if state == "ready_pickup":
            ready_actions = (
                _action(
                    ref="pickup",
                    kind="instruction",
                    label=_copy_title("TRACKING_ACTION_READY_PICKUP", "Retirar pedido"),
                    priority="primary",
                ),
            )
        return OrderTrackingPromiseProjection(
            state=state,
            title=title,
            message=message,
            tone="success",
            deadline_at=None,
            deadline_kind=None,
            timer_mode="none",
            deadline_action="none",
            requires_active_notification=False,
            notification_topic=None,
            actions=ready_actions,
            next_event=(
                _copy_message("TRACKING_PROMISE_READY_DELIVERY_NEXT", "Assim que sair para entrega, avisamos você.")
                if state == "ready_delivery"
                else _copy_message("TRACKING_PROMISE_READY_PICKUP_NEXT", "Retire no estabelecimento quando puder.")
            ),
        )

    state_by_status = {
        "dispatched": (
            "dispatched",
            "TRACKING_STEP_DISPATCHED",
            "Seu pedido saiu para entrega.",
            "info",
            _copy_message("TRACKING_PROMISE_DISPATCHED_MESSAGE", "Estamos acompanhando a entrega."),
            _copy_message("TRACKING_PROMISE_DISPATCHED_NEXT", "Quando for entregue, atualizaremos o pedido."),
        ),
        "delivered": (
            "delivered",
            "TRACKING_STEP_DELIVERED",
            "Seu pedido foi entregue.",
            "success",
            "",
            _copy_message("TRACKING_PROMISE_DELIVERED_NEXT", "O pedido será concluído em seguida."),
        ),
        "completed": (
            "completed",
            "TRACKING_STEP_COMPLETED",
            "O pedido foi concluído.",
            "success",
            "",
            "",
        ),
        "cancelled": (
            "cancelled",
            "TRACKING_STEP_CANCELLED",
            "O pedido foi cancelado.",
            "danger",
            "",
            "",
        ),
    }
    if order.status in state_by_status:
        state, copy_key, fallback, tone, message, next_event = state_by_status[order.status]
        return OrderTrackingPromiseProjection(
            state=state,
            title=_copy_title(copy_key, fallback),
            message=message,
            tone=tone,
            deadline_at=None,
            deadline_kind=None,
            timer_mode="none",
            deadline_action="none",
            requires_active_notification=state in {"dispatched", "delivered"},
            notification_topic=(
                "order_dispatched"
                if state == "dispatched"
                else "order_delivered" if state == "delivered" else None
            ),
            actions=(),
            next_event=next_event,
            active_notification=(
                _copy_message("TRACKING_PROMISE_ACTIVE_UPDATE_NOTIFICATION", "Avisamos ativamente sobre esta atualização.")
                if state in {"dispatched", "delivered"}
                else ""
            ),
        )

    return OrderTrackingPromiseProjection(
        state="received",
        title=_copy_title("TRACKING_STEP_RECEIVED", "Recebemos seu pedido."),
        message=_copy_message(
            "TRACKING_PROMISE_AVAILABILITY_MESSAGE",
            "O estabelecimento está conferindo a disponibilidade.",
        ),
        tone="info",
        deadline_at=None,
        deadline_kind=None,
        timer_mode="none",
        deadline_action="none",
        requires_active_notification=False,
        notification_topic=None,
        actions=(),
        next_event=_copy_message("TRACKING_PROMISE_RECEIVED_NEXT", "O estabelecimento vai conferir a disponibilidade."),
    )


def _copy_pair(key: str, fallback_title: str, fallback_message: str = "") -> tuple[str, str]:
    try:
        entry = resolve_copy(key, moment="*", audience="*")
        return entry.title or fallback_title, entry.message or fallback_message
    except Exception:
        logger.debug("order_tracking_copy_failed key=%s", key, exc_info=True)
        return fallback_title, fallback_message


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


def _tracking_copy() -> OrderTrackingCopyProjection:
    return OrderTrackingCopyProjection(
        page_kicker=_copy_title("TRACKING_PAGE_KICKER", "Acompanhamento"),
        order_ref_label=_copy_title("TRACKING_ORDER_REF_LABEL", "Pedido"),
        menu_label=_copy_title("TRACKING_MENU_CTA", "Ver cardápio"),
        support_label=_copy_title("TRACKING_SUPPORT_CTA", "Ajuda"),
        progress_heading=_copy_title("TRACKING_PROGRESS_HEADING", "Progresso"),
        live_badge=_copy_title("TRACKING_LIVE_BADGE", "Ao vivo"),
        polling_badge=_copy_title("TRACKING_POLLING_BADGE", "Atualização periódica"),
        finished_badge=_copy_title("TRACKING_FINISHED_BADGE", "Finalizado"),
        items_heading=_copy_title("TRACKING_ITEMS_HEADING", "Itens do pedido"),
        total_label=_copy_title("TRACKING_TOTAL_LABEL", "Total"),
        delivery_fee_label=_copy_title("TRACKING_DELIVERY_FEE_LABEL", "Entrega"),
        promise_fallback_message=_copy_message(
            "TRACKING_PROMISE_FALLBACK_MESSAGE",
            "Acompanhando atualizações do pedido.",
        ),
        payment_confirmed_notice=_copy_message(
            "TRACKING_PAYMENT_CONFIRMED_NOTICE",
            "Pagamento confirmado. Acompanhe o próximo passo nesta página.",
        ),
        retry_label=_copy_title("TRACKING_RETRY_CTA", "Tentar novamente"),
        not_found_title=_copy_title("TRACKING_NOT_FOUND_TITLE", "Pedido não encontrado"),
        not_found_description=_copy_message(
            "TRACKING_NOT_FOUND_MESSAGE",
            "Confira o link do pedido ou fale com a equipe.",
        ),
        rate_limit_title=_copy_title("TRACKING_RATE_LIMIT_TITLE", "Atualização pausada por um instante"),
        cancel_success_title=_copy_title("TRACKING_CANCEL_SUCCESS_TITLE", "Pedido cancelado"),
        cancel_success_message=_copy_message(
            "TRACKING_CANCEL_SUCCESS_MESSAGE",
            "Recebemos o cancelamento. Acompanhe o status nesta página.",
        ),
        cancel_failed_message=_copy_message(
            "TRACKING_CANCEL_FAILED_MESSAGE",
            "Não foi possível cancelar este pedido agora.",
        ),
        mock_payment_success_title=_copy_title("TRACKING_MOCK_PAYMENT_SUCCESS_TITLE", "Pagamento teste capturado"),
        mock_payment_success_message=_copy_message(
            "TRACKING_MOCK_PAYMENT_SUCCESS_MESSAGE",
            "Atualizamos o pedido com o estado financeiro simulado.",
        ),
        mock_payment_failed_title=_copy_title(
            "TRACKING_MOCK_PAYMENT_FAILED_TITLE",
            "Não foi possível capturar o pagamento teste",
        ),
        mock_payment_failed_message=_copy_message(
            "TRACKING_MOCK_PAYMENT_FAILED_MESSAGE",
            "Atualize o pedido e tente novamente.",
        ),
        rating_success_title=_copy_title("TRACKING_RATING_SUCCESS_TITLE", "Avaliação registrada"),
        rating_failed_message=_copy_message(
            "TRACKING_RATING_FAILED_MESSAGE",
            "Não foi possível registrar a avaliação agora.",
        ),
        rating_comment_placeholder=_copy_title("TRACKING_RATING_COMMENT_PLACEHOLDER", "Comentário opcional"),
        rating_comment_aria_label=_copy_title("TRACKING_RATING_COMMENT_ARIA_LABEL", "Comentário da avaliação"),
        rating_submit_label=_copy_title("TRACKING_RATING_SUBMIT_CTA", "Enviar avaliação"),
    )


def _fmt_timestamp(dt) -> str:
    try:
        local = timezone.localtime(dt)
        return local.strftime("%d/%m às %H:%M")
    except Exception:
        logger.debug("order_tracking._fmt_timestamp degraded; using fallback", exc_info=True)
        return str(dt)


def _build_timeline(order) -> tuple[TimelineEventProjection, ...]:
    raw: list[tuple] = []

    for event in order.events.order_by("seq"):
        payload = event.payload or {}
        status_key = payload.get("new_status", "")

        if event.type == "status_changed" and status_key:
            label = ORDER_STATUS_LABELS_PT.get(status_key, status_key)
        else:
            label = EVENT_LABELS.get(event.type)
            if label is None:
                label = event.type.replace(".", " ").replace("_", " ").title()

        raw.append((event.created_at, label, event.type))

    for ful in order.fulfillments.all():
        if ful.dispatched_at:
            raw.append((ful.dispatched_at, "Enviado", "fulfillment.dispatched"))
        if ful.delivered_at:
            raw.append((ful.delivered_at, "Entregue", "fulfillment.delivered"))

    raw.sort(key=lambda x: x[0])
    return tuple(
        TimelineEventProjection(
            label=label,
            event_type=event_type,
            timestamp_display=_fmt_timestamp(created_at),
        )
        for created_at, label, event_type in raw
    )


def _build_progress_steps(
    order,
    *,
    is_delivery: bool | None = None,
    is_pickup: bool | None = None,
    payment_confirmed: bool | None = None,
) -> tuple[OrderProgressStepProjection, ...]:
    """Build the customer-facing operational progress path.

    This is intentionally separate from ``timeline``. Timeline is audit
    history; this is the stable path the customer uses to understand what is
    done, what is current, and what is still ahead.
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

    specs: list[tuple[str, str, str | None]] = [
        (
            "received",
            _copy_title("TRACKING_STEP_RECEIVED", "Recebemos seu pedido."),
            _fmt_timestamp(order.created_at),
        ),
        (
            "availability",
            _copy_title("TRACKING_STEP_AVAILABILITY_CONFIRMED", "Confirmamos a disponibilidade."),
            _progress_timestamp(order, "confirmed"),
        ),
    ]
    if include_payment:
        specs.append(
            (
                "payment",
                _copy_title("TRACKING_STEP_PAYMENT_CONFIRMED", "Reconhecemos o pagamento."),
                _payment_confirmed_timestamp(order),
            )
        )
    specs.append(
        (
            "preparing",
            _copy_title("TRACKING_STEP_PREPARING", "Estamos preparando seu pedido."),
            _progress_timestamp(order, "preparing"),
        )
    )
    if is_delivery:
        specs.extend(
            [
                (
                    "ready_delivery",
                    _copy_title(
                        "TRACKING_STEP_READY_DELIVERY",
                        "Seu pedido está pronto e aguardando entregador.",
                    ),
                    _progress_timestamp(order, "ready"),
                ),
                (
                    "dispatched",
                    _copy_title("TRACKING_STEP_DISPATCHED", "Seu pedido saiu para entrega."),
                    _progress_timestamp(order, "dispatched"),
                ),
                (
                    "delivered",
                    _copy_title("TRACKING_STEP_DELIVERED", "Seu pedido foi entregue."),
                    _progress_timestamp(order, "delivered"),
                ),
                (
                    "completed",
                    _copy_title("TRACKING_STEP_COMPLETED", "O pedido foi concluído."),
                    _progress_timestamp(order, "completed"),
                ),
            ]
        )
    elif is_pickup:
        specs.extend(
            [
                (
                    "ready",
                    _copy_title("TRACKING_STEP_READY_PICKUP", "Seu pedido está pronto para retirada."),
                    _progress_timestamp(order, "ready"),
                ),
                (
                    "completed",
                    _copy_title("TRACKING_STEP_COMPLETED", "O pedido foi concluído."),
                    _progress_timestamp(order, "completed"),
                ),
            ]
        )
    else:
        specs.extend(
            [
                (
                    "ready",
                    _copy_title("TRACKING_STEP_READY_GENERIC", "Seu pedido está pronto."),
                    _progress_timestamp(order, "ready"),
                ),
                (
                    "completed",
                    _copy_title("TRACKING_STEP_COMPLETED", "O pedido foi concluído."),
                    _progress_timestamp(order, "completed"),
                ),
            ]
        )
    if cancelled:
        specs[-1] = (
            "cancelled",
            _copy_title("TRACKING_STEP_CANCELLED", "O pedido foi cancelado."),
            _progress_timestamp(order, "cancelled"),
        )

    active_index = next((idx for idx, (key, _, _) in enumerate(specs) if key == active_key), 0)
    steps: list[OrderProgressStepProjection] = []
    for idx, (key, label, timestamp) in enumerate(specs):
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
        steps.append(
            OrderProgressStepProjection(
                label=label,
                key=key,
                state=state,
                timestamp_display=timestamp,
            )
        )
    return tuple(step for step in steps if _should_render_progress_step(step))


def _should_render_progress_step(step: OrderProgressStepProjection) -> bool:
    if step.state == "pending":
        return False
    if step.key == "received":
        return True
    return bool(step.timestamp_display)


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
    field = f"{status}_at"
    value = getattr(order, field, None)
    if value:
        return _fmt_timestamp(value)
    if status == "confirmed":
        event = _event_for_status(order, "confirmed")
    elif status in {"preparing", "ready", "dispatched", "delivered", "completed", "cancelled"}:
        event = _event_for_status(order, status)
    else:
        event = None
    if event:
        return _fmt_timestamp(event.created_at)
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
        return _fmt_timestamp(captured_at)
    event = order.events.filter(type="payment.captured").order_by("created_at", "seq").first()
    if event:
        return _fmt_timestamp(event.created_at)
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
                return _fmt_timestamp(intent.captured_at)
    return None


def _build_items(order) -> tuple[OrderItemProjection, ...]:
    return tuple(
        OrderItemProjection(
            sku=item.sku,
            name=item.name or item.sku,
            qty=int(item.qty),
            unit_price_display=f"R$ {format_money(item.unit_price_q)}",
            total_display=f"R$ {format_money(item.line_total_q)}",
        )
        for item in order.items.all()
    )


def _build_fulfillments(
    order,
    *,
    is_delivery: bool | None = None,
    is_pickup: bool | None = None,
) -> tuple[tuple[FulfillmentProjection, ...], tuple[FulfillmentProjection, ...]]:
    delivery: list[FulfillmentProjection] = []
    pickup: list[FulfillmentProjection] = []
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
        projected = FulfillmentProjection(
            status=ful.status,
            status_label=FULFILLMENT_STATUS_LABELS.get(ful.status, ful.status),
            tracking_label=_fulfillment_tracking_label(ful.carrier),
            tracking_code=ful.tracking_code or None,
            tracking_url=tracking_url,
            carrier=ful.carrier or None,
            dispatched_at_display=_fmt_timestamp(ful.dispatched_at) if ful.dispatched_at else None,
            delivered_at_display=_fmt_timestamp(ful.delivered_at) if ful.delivered_at else None,
        )
        if is_delivery or ful.carrier or ful.tracking_code:
            delivery.append(projected)
        elif is_pickup:
            pickup.append(projected)

    return tuple(delivery), tuple(pickup)


def _pickup_info() -> PickupInfoProjection | None:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        if not shop:
            return None

        hours_list = _format_opening_hours()
        hours_str = "; ".join(f"{hour['label']}: {hour['hours']}" for hour in hours_list)
        directions_url = _pickup_directions_url(shop)
        address = _pickup_display_address(shop)
        if not (address or hours_str or directions_url):
            return None
        return PickupInfoProjection(
            heading=_copy_title("TRACKING_PICKUP_HEADING", "Retirada"),
            address=address,
            opening_hours=hours_str,
            directions_label=_copy_title("TRACKING_PICKUP_DIRECTIONS_CTA", "Como chegar"),
            directions_url=directions_url,
        )
    except Exception:
        logger.warning("order_tracking_pickup_info_failed", exc_info=True)
        return None


def _pickup_directions_url(shop) -> str | None:
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
        str(getattr(shop, field, "") or "").strip()
        for field in ("route", "street_number", "neighborhood", "postal_code")
    )


def _fulfillment_tracking_label(carrier: str | None) -> str:
    if carrier:
        template = _copy_title("TRACKING_TRACK_SHIPMENT_WITH_CARRIER", "Acompanhar via {carrier}")
        return template.format(carrier=carrier)
    return _copy_title("TRACKING_TRACK_SHIPMENT", "Rastrear envio")


def _format_opening_hours() -> list[dict]:
    from shopman.shop.models import Shop

    shop = Shop.load()
    if not shop or not shop.opening_hours:
        return []

    def _fmt_time(value: str) -> str:
        parts = value.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        if minute:
            return f"{hour}h{minute:02d}"
        return f"{hour}h"

    day_hours: list[tuple[str, str]] = []
    for day in DAY_ORDER:
        info = shop.opening_hours.get(day)
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
    return result


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


def _eta_display(order) -> str | None:
    if order.status != "preparing":
        return None
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        prep_minutes = getattr(shop, "prep_time_minutes", None) or 30
        baseline = getattr(order, "preparing_at", None)
        if baseline is None:
            event = _event_for_status(order, "preparing")
            baseline = event.created_at if event else None
        if baseline is None:
            return None
        eta = timezone.localtime(baseline) + timezone.timedelta(minutes=prep_minutes)
        return eta.strftime("%H:%M")
    except Exception:
        logger.debug("order_tracking_eta_failed order=%s", order.ref, exc_info=True)
        return None


def _contact_and_share(order) -> tuple[str, str, str]:
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

    support_url = whatsapp_url
    if support_url:
        support_message = _copy_message(
            "TRACKING_SUPPORT_WHATSAPP_MESSAGE",
            "Oi! Posso ajudar com o pedido {order_ref}?",
        ).format(order_ref=order.ref)
        separator = "&" if "?" in support_url else "?"
        support_url = f"{support_url}{separator}{urlencode({'text': support_message})}"

    return whatsapp_url, support_url, f"Meu pedido {order.ref} na {shop_name}"


__all__ = [
    "OrderTrackingProjection",
    "OrderTrackingPromiseProjection",
    "OrderTrackingPromiseRowProjection",
    "OrderTrackingStatusProjection",
    "PickupInfoProjection",
    "build_tracking",
    "build_tracking_status",
]
