"""POS command facade.

Backstage POS views own permissions, HTTP parsing, and HTML responses. This
module owns the Orderman session writes and POS order commands.
"""

from __future__ import annotations

import logging
import secrets
import string
from dataclasses import dataclass
from datetime import timedelta

from django.utils import timezone
from shopman.orderman.models import Order, Session

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel, Shop
from shopman.shop.services import sessions as session_service
from shopman.shop.services.cancellation import cancel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PosSaleResult:
    order_ref: str
    total_q: int


@dataclass(frozen=True)
class PosParkResult:
    tab: str
    session_key: str


def resolve_customer(phone: str):
    """Look up a customer by phone for POS display and pricing modifiers."""
    if not phone:
        return None
    try:
        from shopman.guestman.services import customer as customer_service

        return customer_service.get_by_phone(phone)
    except Exception:
        logger.exception("pos_resolve_customer_failed phone=%s", phone)
        return None


def close_sale(
    *,
    channel_ref: str,
    payload: dict,
    actor: str,
    operator_username: str,
) -> PosSaleResult:
    """Create and commit a POS sale from a parsed cart payload."""
    channel, config = _channel_and_config(channel_ref)
    customer_phone = str(payload.get("customer_phone", "") or "").strip()

    session = session_service.create_session(
        channel.ref,
        handle_type="pos" if not customer_phone else "phone",
        handle_ref=customer_phone or f"pos:{operator_username}",
    )

    ops = build_session_ops(payload, operator_username)
    ops.extend([
        {"op": "set_data", "path": "origin_channel", "value": "pos"},
        {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
    ])

    session_service.modify_session(
        session_key=session.session_key,
        channel_ref=channel.ref,
        ops=ops,
        ctx={"actor": actor},
        channel_config=config.to_dict(),
    )

    result = session_service.commit_session(
        session_key=session.session_key,
        channel_ref=channel.ref,
        idempotency_key=session_service.new_idempotency_key(),
        ctx={"actor": actor},
        channel_config=config.to_dict(),
    )
    logger.info("pos_close order=%s total=%s", result.order_ref, result.total_q)
    return PosSaleResult(order_ref=result.order_ref, total_q=result.total_q)


def park_session(
    *,
    channel_ref: str,
    payload: dict,
    actor: str,
    operator_username: str,
) -> PosParkResult:
    """Save the current POS cart as a standby session."""
    channel, config = _channel_and_config(channel_ref)

    shop = Shop.load()
    tab = _generate_pos_tab(shop_id=str(shop.pk) if shop else "")

    session = session_service.create_session(
        channel.ref,
        handle_type="pos",
        handle_ref=f"pos:{operator_username}",
    )
    session_service.assign_handle(
        session_key=session.session_key,
        channel_ref=channel.ref,
        handle_type="pos",
        handle_ref=f"pos:{operator_username}:{session.session_key[:8]}",
    )

    ops = build_session_ops(payload, operator_username)
    ops.extend([
        {"op": "set_data", "path": "standby", "value": True},
        {"op": "set_data", "path": "tab", "value": tab},
        {"op": "set_data", "path": "standby_operator", "value": operator_username},
    ])

    session_service.modify_session(
        session_key=session.session_key,
        channel_ref=channel.ref,
        ops=ops,
        ctx={"actor": actor},
        channel_config=config.to_dict(),
    )
    logger.info("pos_park tab=%s session=%s operator=%s", tab, session.session_key, operator_username)
    return PosParkResult(tab=tab, session_key=session.session_key)


def _generate_pos_tab(*, shop_id: str) -> str:
    scope = {
        "store_id": shop_id,
        "business_date": timezone.localdate().isoformat(),
    }
    try:
        from shopman.refs.generators import generate_value

        return generate_value("POS_TAB", scope)
    except (ImportError, LookupError):
        alphabet = string.ascii_uppercase.replace("O", "").replace("I", "") + string.digits.replace("0", "").replace("1", "")
        suffix = "".join(secrets.choice(alphabet) for _ in range(4))
        return f"TAB-{timezone.localdate():%y%m%d}-{suffix}"


def standby_sessions(*, channel_ref: str, business_date=None) -> list[dict]:
    """Return open standby POS sessions for display."""
    from shopman.utils.monetary import format_money

    business_date = business_date or timezone.localdate()
    sessions_qs = Session.objects.filter(
        channel_ref=channel_ref,
        state="open",
        data__standby=True,
        opened_at__date=business_date,
    ).order_by("opened_at")

    sessions = []
    for session in sessions_qs:
        data = session.data or {}
        items = session.items or []
        item_count = sum(int(item.get("qty", 1)) for item in items)
        total_q = sum(
            int(item.get("qty", 1)) * int(item.get("unit_price_q", 0))
            for item in items
        )
        discount_q = int((data.get("manual_discount") or {}).get("discount_q", 0))
        sessions.append({
            "session_key": session.session_key,
            "tab": data.get("tab", "?"),
            "item_count": item_count,
            "total_display": f"R$ {format_money(max(0, total_q - discount_q))}",
            "customer_name": (data.get("customer") or {}).get("name", ""),
        })
    return sessions


def load_standby_session(*, channel_ref: str, session_key: str) -> dict | None:
    """Load a standby session payload and mark it as no longer standby."""
    session = Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).first()
    if session is None:
        return None

    data = session.data or {}
    customer = data.get("customer") or {}
    payment = data.get("payment") or {}
    discount = data.get("manual_discount") or {}
    items = [
        {
            "sku": item["sku"],
            "name": item.get("name", item["sku"]),
            "price_q": item.get("unit_price_q", 0),
            "qty": int(item.get("qty", 1)),
            "note": (item.get("meta") or {}).get("note", ""),
            "is_d1": False,
        }
        for item in (session.items or [])
    ]

    data["standby"] = False
    session.data = data
    session.save(update_fields=["data"])

    return {
        "session_key": session_key,
        "tab": data.get("tab", ""),
        "items": items,
        "customer_phone": customer.get("phone", ""),
        "customer_name": customer.get("name", ""),
        "customer_group": customer.get("group", ""),
        "payment_method": payment.get("method", "cash"),
        "discount_type": discount.get("type", "percent"),
        "discount_value": str(discount.get("value", "")) if discount.get("value") else "",
        "discount_reason": discount.get("reason", "cortesia"),
    }


def cancel_recent_order(
    *,
    order_ref: str,
    actor: str,
    max_age_minutes: int = 5,
) -> None:
    """Cancel the last POS order if it is still inside the operator window."""
    try:
        order = Order.objects.get(ref=order_ref)
    except Order.DoesNotExist as exc:
        raise ValueError(f"Pedido {order_ref} não encontrado") from exc

    age = timezone.now() - order.created_at
    if age > timedelta(minutes=max_age_minutes):
        raise ValueError(
            f"Pedido {order_ref} criado há mais de {max_age_minutes} minutos — cancelamento não permitido"
        )
    if order.status not in (Order.Status.NEW, Order.Status.CONFIRMED):
        raise ValueError(f"Pedido {order_ref} não pode ser cancelado (status: {order.status})")

    cancel(order, reason="pos_operator", actor=actor)
    logger.info("pos_cancel_last order=%s actor=%s", order_ref, actor)


def build_session_ops(payload: dict, operator_username: str) -> list[dict]:
    """Build canonical Orderman session ops from a POS cart payload."""
    ops = []
    for item in payload.get("items", []):
        op = {
            "op": "add_line",
            "sku": item["sku"],
            "qty": int(item.get("qty", 1)),
            "unit_price_q": int(item["unit_price_q"]),
        }
        note = str(item.get("note", "") or "").strip()
        if note:
            op["meta"] = {"note": note}
        ops.append(op)

    customer_name = str(payload.get("customer_name", "") or "").strip()
    customer_phone = str(payload.get("customer_phone", "") or "").strip()
    if customer_name:
        ops.append({"op": "set_data", "path": "customer.name", "value": customer_name})
    if customer_phone:
        ops.append({"op": "set_data", "path": "customer.phone", "value": customer_phone})

    customer = resolve_customer(customer_phone)
    if customer:
        ops.append({"op": "set_data", "path": "customer.ref", "value": customer.ref})
        if customer.group_id:
            ops.append({"op": "set_data", "path": "customer.group", "value": customer.group.ref})

    payment_method = payload.get("payment_method", "cash")
    ops.append({"op": "set_data", "path": "payment.method", "value": payment_method})

    tendered_amount_q = payload.get("tendered_amount_q")
    if tendered_amount_q and payment_method == "cash":
        ops.append({"op": "set_data", "path": "payment.tendered_q", "value": int(tendered_amount_q)})

    manual_discount = payload.get("manual_discount") or {}
    if manual_discount and int(manual_discount.get("discount_q", 0)) > 0:
        ops.extend([
            {"op": "set_data", "path": "manual_discount.type", "value": manual_discount.get("type", "percent")},
            {"op": "set_data", "path": "manual_discount.value", "value": manual_discount.get("value", 0)},
            {"op": "set_data", "path": "manual_discount.discount_q", "value": int(manual_discount.get("discount_q", 0))},
            {"op": "set_data", "path": "manual_discount.reason", "value": manual_discount.get("reason", "")},
        ])
    return ops


def _channel_and_config(channel_ref: str) -> tuple[Channel, ChannelConfig]:
    try:
        channel = Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist as exc:
        raise ValueError(f"Canal {channel_ref} não configurado. Contacte o suporte.") from exc
    return channel, ChannelConfig.for_channel(channel)
