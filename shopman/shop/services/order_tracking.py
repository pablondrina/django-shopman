"""Canonical order tracking read models for customer-facing surfaces."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone
from shopman.utils.monetary import format_money

from shopman.shop.projections.types import (
    ORDER_STATUS_COLORS,
    ORDER_STATUS_LABELS_PT,
    FulfillmentProjection,
    OrderItemProjection,
    TimelineEventProjection,
)
from shopman.shop.services import payment_status

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
class PickupInfoReadModel:
    """Store address and hours shown when the fulfillment type is pickup."""

    address: str
    opening_hours: str
    google_maps_url: str | None


@dataclass(frozen=True)
class OrderTrackingReadModel:
    """Canonical full tracking read model."""

    order_ref: str
    status: str
    status_label: str
    status_color: str
    timeline: tuple[TimelineEventProjection, ...]
    items: tuple[OrderItemProjection, ...]
    total_display: str
    delivery_fee_display: str | None
    is_delivery: bool
    delivery_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_fulfillments: tuple[FulfillmentProjection, ...]
    pickup_info: PickupInfoReadModel | None
    can_cancel: bool
    is_active: bool
    confirmation_countdown: bool
    confirmation_expires_at: str | None
    eta_display: str | None
    whatsapp_url: str
    share_text: str
    is_debug: bool


@dataclass(frozen=True)
class OrderTrackingStatusReadModel:
    """Canonical polling read model for tracking status partials."""

    order_ref: str
    status: str
    status_label: str
    status_color: str
    timeline: tuple[TimelineEventProjection, ...]
    is_terminal: bool
    can_cancel: bool


def build_tracking(order, *, is_debug: bool = False) -> OrderTrackingReadModel:
    """Build the full tracking read model for an order."""
    status_label, status_color = _status_display(order)
    timeline = _build_timeline(order)
    items = _build_items(order)
    delivery_fulfillments, pickup_fulfillments = _build_fulfillments(order)
    pickup_info = _pickup_info() if pickup_fulfillments else None

    order_data = order.data or {}
    delivery_fee_q = order_data.get("delivery_fee_q")
    delivery_fee_display: str | None = None
    if delivery_fee_q is not None:
        delivery_fee_display = "Grátis" if delivery_fee_q == 0 else f"R$ {format_money(delivery_fee_q)}"

    fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
    is_delivery = fulfillment_type == "delivery"

    confirmation_countdown, confirmation_expires_at = _confirmation_info(order)
    whatsapp_url, share_text = _contact_and_share(order)

    return OrderTrackingReadModel(
        order_ref=order.ref,
        status=order.status,
        status_label=status_label,
        status_color=status_color,
        timeline=timeline,
        items=items,
        total_display=f"R$ {format_money(order.total_q)}",
        delivery_fee_display=delivery_fee_display,
        is_delivery=is_delivery,
        delivery_fulfillments=delivery_fulfillments,
        pickup_fulfillments=pickup_fulfillments,
        pickup_info=pickup_info,
        can_cancel=payment_status.can_cancel(order),
        is_active=order.status not in TERMINAL_STATUSES,
        confirmation_countdown=confirmation_countdown,
        confirmation_expires_at=confirmation_expires_at,
        eta_display=_eta_display(order),
        whatsapp_url=whatsapp_url,
        share_text=share_text,
        is_debug=is_debug,
    )


def build_tracking_status(order) -> OrderTrackingStatusReadModel:
    """Build the polling read model for tracking status partials."""
    status_label, status_color = _status_display(order)
    return OrderTrackingStatusReadModel(
        order_ref=order.ref,
        status=order.status,
        status_label=status_label,
        status_color=status_color,
        timeline=_build_timeline(order),
        is_terminal=order.status in TERMINAL_STATUSES,
        can_cancel=payment_status.can_cancel(order),
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

    label = ORDER_STATUS_LABELS_PT.get(order.status, order.status)
    if order.status == "ready":
        label = "Aguardando entregador" if is_delivery else "Pronto para retirada"
    elif order.status == "completed":
        label = "Entregue" if is_delivery else "Concluído"

    color = ORDER_STATUS_COLORS.get(order.status, "bg-surface-alt text-on-surface/60 border border-outline")
    return label, color


def _fmt_timestamp(dt) -> str:
    try:
        local = timezone.localtime(dt)
        return local.strftime("%d/%m às %H:%M")
    except Exception:
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
) -> tuple[tuple[FulfillmentProjection, ...], tuple[FulfillmentProjection, ...]]:
    delivery: list[FulfillmentProjection] = []
    pickup: list[FulfillmentProjection] = []

    for ful in order.fulfillments.all():
        tracking_url = ful.tracking_url or _carrier_tracking_url(ful.carrier, ful.tracking_code)
        projected = FulfillmentProjection(
            status=ful.status,
            status_label=FULFILLMENT_STATUS_LABELS.get(ful.status, ful.status),
            tracking_code=ful.tracking_code or None,
            tracking_url=tracking_url,
            carrier=ful.carrier or None,
            dispatched_at_display=_fmt_timestamp(ful.dispatched_at) if ful.dispatched_at else None,
            delivered_at_display=_fmt_timestamp(ful.delivered_at) if ful.delivered_at else None,
        )
        if ful.carrier or ful.tracking_code:
            delivery.append(projected)
        else:
            pickup.append(projected)

    return tuple(delivery), tuple(pickup)


def _pickup_info() -> PickupInfoReadModel | None:
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        if not shop:
            return None

        hours_list = _format_opening_hours()
        hours_str = "; ".join(f"{hour['label']}: {hour['hours']}" for hour in hours_list)
        google_maps_url = None
        if shop.latitude and shop.longitude:
            google_maps_url = (
                f"https://www.google.com/maps/dir/?api=1&destination={shop.latitude},{shop.longitude}"
            )
        return PickupInfoReadModel(
            address=shop.formatted_address or "",
            opening_hours=hours_str,
            google_maps_url=google_maps_url,
        )
    except Exception:
        logger.warning("order_tracking_pickup_info_failed", exc_info=True)
        return None


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


def _confirmation_info(order) -> tuple[bool, str | None]:
    if order.status != "new":
        return False, None
    try:
        from shopman.shop.config import ChannelConfig

        cfg = ChannelConfig.for_channel(order.channel_ref).confirmation
        if cfg.mode == "auto_confirm":
            expires_at = order.created_at + timedelta(minutes=cfg.timeout_minutes)
            return True, expires_at.isoformat()
    except Exception:
        logger.warning("order_tracking_confirmation_failed order=%s", order.ref, exc_info=True)
    return False, None


def _eta_display(order) -> str | None:
    if order.status != "preparing":
        return None
    try:
        from shopman.shop.models import Shop

        shop = Shop.load()
        prep_minutes = getattr(shop, "prep_time_minutes", None) or 30
        eta = timezone.localtime(order.created_at) + timezone.timedelta(minutes=prep_minutes)
        return eta.strftime("%H:%M")
    except Exception:
        logger.debug("order_tracking_eta_failed order=%s", order.ref, exc_info=True)
        return None


def _contact_and_share(order) -> tuple[str, str]:
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

    return whatsapp_url, f"Meu pedido {order.ref} na {shop_name}"


__all__ = [
    "OrderTrackingReadModel",
    "OrderTrackingStatusReadModel",
    "PickupInfoReadModel",
    "build_tracking",
    "build_tracking_status",
]
