"""POS command facade.

Backstage POS views own permissions, HTTP parsing, and HTML responses. This
module owns the Orderman session writes and POS order commands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from shopman.orderman.models import Order, Session

from shopman.shop.adapters import pos as pos_adapter
from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel
from shopman.shop.services import sessions as session_service
from shopman.shop.services.cancellation import cancel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PosSaleResult:
    order_ref: str
    total_q: int


@dataclass(frozen=True)
class PosTabResult:
    tab_code: str
    tab_display: str
    session_key: str


def normalize_tab_code(value: str) -> str:
    """Normalize a POS tab number to the stored 8-digit code."""
    raw = str(value or "").strip()
    if not raw or not raw.isdigit() or len(raw) > 8:
        raise ValueError("Informe um POS tab com até 8 dígitos.")
    return raw.zfill(8)


def display_tab_code(tab_code: str) -> str:
    return str(tab_code or "").lstrip("0") or "0"


def register_pos_tab(*, tab_code: str, label: str = "") -> dict:
    """Register or reactivate a POS tab without opening a sale session."""
    code = normalize_tab_code(tab_code)
    display = display_tab_code(code)
    label = str(label or "").strip()
    return pos_adapter.upsert_tab(code=code, label=label, display=display)


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
    session = _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
    if session is None:
        raise ValueError("Abra um POS tab antes de finalizar.")

    tab_code = _session_tab_code(session)
    ops = _replace_session_ops(session, payload, operator_username)
    ops.extend([
        {"op": "set_data", "path": "origin_channel", "value": "pos"},
        {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        {"op": "set_data", "path": "tab_code", "value": tab_code},
        {"op": "set_data", "path": "tab_display", "value": display_tab_code(tab_code)},
        {"op": "set_data", "path": "pos_operator", "value": operator_username},
        {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
    ])

    session = session_service.modify_session(
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
    _mark_tab_committed(
        order_ref=result.order_ref,
        tab_code=tab_code,
        operator_username=operator_username,
        session_data=session.data,
    )
    logger.info("pos_close_tab order=%s tab=%s session=%s total=%s", result.order_ref, tab_code, session.session_key, result.total_q)
    return PosSaleResult(order_ref=result.order_ref, total_q=result.total_q)


def open_pos_tab(
    *,
    channel_ref: str,
    tab_code: str,
    actor: str,
    operator_username: str,
) -> dict:
    """Open or load the current order for a POS tab."""
    channel, config = _channel_and_config(channel_ref)
    code = normalize_tab_code(tab_code)
    _ensure_pos_tab(code)
    session = _get_open_pos_tab_session(channel_ref=channel.ref, tab_code=code)
    if session is None:
        session = session_service.create_session(
            channel.ref,
            handle_type="pos_tab",
            handle_ref=code,
            data={
                "origin_channel": "pos",
                "fulfillment_type": "pickup",
                "tab_code": code,
                "tab_display": display_tab_code(code),
                "pos_operator": operator_username,
                "last_touched_at": timezone.now().isoformat(),
            },
        )
    else:
        session_service.assign_handle(
            session_key=session.session_key,
            channel_ref=channel.ref,
            handle_type="pos_tab",
            handle_ref=code,
        )
        session_service.modify_session(
            session_key=session.session_key,
            channel_ref=channel.ref,
            ops=[
                {"op": "set_data", "path": "tab_code", "value": code},
                {"op": "set_data", "path": "tab_display", "value": display_tab_code(code)},
                {"op": "set_data", "path": "pos_operator", "value": operator_username},
                {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
            ],
            ctx={"actor": actor},
            channel_config=config.to_dict(),
        )
        session.refresh_from_db()

    logger.info("pos_open_tab tab=%s session=%s operator=%s", code, session.session_key, operator_username)
    return _tab_payload(session)


def save_pos_tab(
    *,
    channel_ref: str,
    payload: dict,
    actor: str,
    operator_username: str,
) -> PosTabResult:
    """Save the current POS cart on its tab and return to the tab grid."""
    channel, config = _channel_and_config(channel_ref)
    session = _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
    if session is None:
        raise ValueError("Abra um POS tab antes de deixar em espera.")

    tab_code = _session_tab_code(session)
    _ensure_pos_tab(tab_code)
    ops = _replace_session_ops(session, payload, operator_username)
    ops.extend([
        {"op": "set_data", "path": "origin_channel", "value": "pos"},
        {"op": "set_data", "path": "fulfillment_type", "value": "pickup"},
        {"op": "set_data", "path": "tab_code", "value": tab_code},
        {"op": "set_data", "path": "tab_display", "value": display_tab_code(tab_code)},
        {"op": "set_data", "path": "pos_operator", "value": operator_username},
        {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
    ])

    session_service.modify_session(
        session_key=session.session_key,
        channel_ref=channel.ref,
        ops=ops,
        ctx={"actor": actor},
        channel_config=config.to_dict(),
    )
    logger.info("pos_save_tab tab=%s session=%s operator=%s", tab_code, session.session_key, operator_username)
    return PosTabResult(tab_code=tab_code, tab_display=display_tab_code(tab_code), session_key=session.session_key)


def clear_pos_tab(*, channel_ref: str, session_key: str, operator_username: str) -> bool:
    """Abandon the open POS tab session, making the tab empty again."""
    session = _get_open_pos_tab_session_by_key(channel_ref=channel_ref, session_key=session_key)
    if session is None:
        return False
    cleared = session_service.abandon_session(session_key=session.session_key, channel_ref=channel_ref)
    if cleared:
        logger.info("pos_clear_tab tab=%s session=%s operator=%s", _session_tab_code(session), session.session_key, operator_username)
    return cleared


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
        name = str(item.get("name", "") or "").strip()
        if name:
            op["name"] = name
        notes = str(item.get("notes", "") or "").strip()
        if notes:
            op["meta"] = {"notes": notes}
        ops.append(op)

    customer_name = str(payload.get("customer_name", "") or "").strip()
    customer_phone = str(payload.get("customer_phone", "") or "").strip()
    customer_tax_id = str(payload.get("customer_tax_id", "") or "").strip()
    if customer_name:
        ops.append({"op": "set_data", "path": "customer.name", "value": customer_name})
    if customer_phone:
        ops.append({"op": "set_data", "path": "customer.phone", "value": customer_phone})
    if customer_tax_id:
        ops.append({"op": "set_data", "path": "customer.tax_id", "value": customer_tax_id})

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

    issue_fiscal_document = bool(payload.get("issue_fiscal_document"))
    ops.append({"op": "set_data", "path": "fiscal.issue_document", "value": issue_fiscal_document})
    if customer_tax_id:
        ops.append({"op": "set_data", "path": "fiscal.tax_id", "value": customer_tax_id})

    receipt_mode = str(payload.get("receipt_mode") or "none").strip() or "none"
    receipt_email = str(payload.get("receipt_email", "") or "").strip()
    ops.append({"op": "set_data", "path": "receipt.mode", "value": receipt_mode})
    if receipt_email:
        ops.append({"op": "set_data", "path": "receipt.email", "value": receipt_email})

    manual_discount = payload.get("manual_discount") or {}
    if manual_discount and int(manual_discount.get("discount_q", 0)) > 0:
        ops.extend([
            {"op": "set_data", "path": "manual_discount.type", "value": manual_discount.get("type", "percent")},
            {"op": "set_data", "path": "manual_discount.value", "value": manual_discount.get("value", 0)},
            {"op": "set_data", "path": "manual_discount.discount_q", "value": int(manual_discount.get("discount_q", 0))},
            {"op": "set_data", "path": "manual_discount.reason", "value": manual_discount.get("reason", "")},
        ])
    return ops


def _replace_session_ops(session: Session, payload: dict, operator_username: str) -> list[dict]:
    """Build ops that replace mutable POS payload fields on an existing session."""
    ops = [
        {"op": "remove_line", "line_id": item["line_id"]}
        for item in (session.items or [])
        if item.get("line_id")
    ]
    ops.extend([
        {"op": "set_data", "path": "customer", "value": {}},
        {"op": "set_data", "path": "payment", "value": {}},
        {"op": "set_data", "path": "fiscal", "value": {}},
        {"op": "set_data", "path": "receipt", "value": {}},
        {"op": "set_data", "path": "manual_discount", "value": {}},
    ])
    ops.extend(build_session_ops(payload, operator_username))
    return ops


def _payload_tab_session_key(payload: dict) -> str:
    return str(payload.get("tab_session_key") or "").strip()


def _payload_tab_code(payload: dict) -> str:
    raw = str(payload.get("tab_code") or "").strip()
    return normalize_tab_code(raw) if raw else ""


def _payload_open_tab_session(*, channel_ref: str, payload: dict) -> Session | None:
    session_key = _payload_tab_session_key(payload)
    if session_key:
        return _get_open_pos_tab_session_by_key(channel_ref=channel_ref, session_key=session_key)
    tab_code = _payload_tab_code(payload)
    if tab_code:
        return _get_open_pos_tab_session(channel_ref=channel_ref, tab_code=tab_code)
    return None


def _get_open_pos_tab_session_by_key(*, channel_ref: str, session_key: str) -> Session | None:
    return Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).first()


def _get_open_pos_tab_session(*, channel_ref: str, tab_code: str) -> Session | None:
    return Session.objects.filter(
        Q(handle_type="pos_tab", handle_ref=tab_code) | Q(data__tab_code=tab_code),
        channel_ref=channel_ref,
        state="open",
    ).order_by("-opened_at").first()


def _session_tab_code(session: Session) -> str:
    data = session.data or {}
    raw = str(data.get("tab_code") or session.handle_ref or "").strip()
    return normalize_tab_code(raw)


def _tab_payload(session: Session) -> dict:
    data = session.data or {}
    customer = data.get("customer") or {}
    payment = data.get("payment") or {}
    fiscal = data.get("fiscal") or {}
    receipt = data.get("receipt") or {}
    discount = data.get("manual_discount") or {}
    tab_code = _session_tab_code(session)
    items = [
        {
            "sku": item["sku"],
            "name": item.get("name", item["sku"]),
            "price_q": item.get("unit_price_q", 0),
            "qty": int(item.get("qty", 1)),
            "notes": (item.get("meta") or {}).get("notes", ""),
            "is_d1": bool(item.get("is_d1")),
        }
        for item in (session.items or [])
    ]

    return {
        "session_key": session.session_key,
        "tab_session_key": session.session_key,
        "tab_code": tab_code,
        "tab_display": display_tab_code(tab_code),
        "items": items,
        "customer_phone": customer.get("phone", ""),
        "customer_name": customer.get("name", ""),
        "customer_group": customer.get("group", ""),
        "customer_tax_id": customer.get("tax_id", ""),
        "payment_method": payment.get("method", "cash"),
        "tendered_amount_q": payment.get("tendered_q", ""),
        "issue_fiscal_document": bool(fiscal.get("issue_document")),
        "receipt_mode": receipt.get("mode", "none"),
        "receipt_email": receipt.get("email", ""),
        "discount_type": discount.get("type", "percent"),
        "discount_value": str(discount.get("value", "")) if discount.get("value") else "",
        "discount_reason": discount.get("reason", "cortesia"),
    }


def _ensure_pos_tab(tab_code: str) -> None:
    pos_adapter.ensure_tab(code=tab_code, display=display_tab_code(tab_code))


def _mark_tab_committed(
    *,
    order_ref: str,
    tab_code: str,
    operator_username: str,
    session_data: dict | None = None,
) -> None:
    now = timezone.now().isoformat()

    order = Order.objects.filter(ref=order_ref).first()
    if order is None:
        return
    order_data = dict(order.data or {})
    order_data["tab_code"] = tab_code
    order_data["tab_display"] = display_tab_code(tab_code)
    order_data["pos_operator"] = operator_username
    order_data["pos_committed_at"] = now

    session_data = session_data or {}
    fiscal = session_data.get("fiscal") or {}
    if fiscal.get("issue_document") or fiscal.get("tax_id"):
        order_data["fiscal"] = fiscal
    receipt = session_data.get("receipt") or {}
    if receipt.get("email") or receipt.get("mode") not in (None, "", "none"):
        order_data["receipt"] = receipt
    manual_discount = session_data.get("manual_discount") or {}
    if manual_discount.get("discount_q"):
        order_data["manual_discount"] = manual_discount

    order.data = order_data
    order.save(update_fields=["data"])


def _channel_and_config(channel_ref: str) -> tuple[Channel, ChannelConfig]:
    try:
        channel = Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist as exc:
        raise ValueError(f"Canal {channel_ref} não configurado. Contacte o suporte.") from exc
    return channel, ChannelConfig.for_channel(channel)
