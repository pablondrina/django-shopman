"""POS mutation facade.

Backstage POS views own permissions, HTTP parsing, and HTML responses. This
module owns the Orderman session writes and POS order mutations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from shopman.orderman.models import Order, Session

from shopman.shop.adapters import pos as pos_adapter
from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel
from shopman.shop.services import sessions as session_service
from shopman.shop.services.cancellation import cancel
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION, PosIntentError, parse_pos_sale_intent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PosSaleResult:
    order_ref: str
    total_q: int
    fiscal_hint: str = ""


@dataclass(frozen=True)
class PosSaleReview:
    intent_version: str
    tab_code: str
    subtotal_q: int
    discount_q: int
    delivery_fee_q: int
    total_q: int
    payment_method: str
    payment_collection: str
    tender_total_q: int
    tender_count: int
    tendered_amount_q: int
    change_q: int
    requires_manager_approval: bool
    manager_approval_threshold_q: int
    receipt_mode: str
    issue_fiscal_document: bool
    warnings: tuple[dict, ...] = ()


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


def customer_history_summary(customer_ref: str, *, limit: int = 5) -> dict:
    """Return compact consumption memory for POS lookup surfaces."""
    if not customer_ref:
        return {}
    try:
        from shopman.orderman.services import CustomerOrderHistoryService

        stats = CustomerOrderHistoryService.get_customer_stats(customer_ref)
        recent = CustomerOrderHistoryService.list_customer_orders(customer_ref, limit=limit)
    except Exception:
        logger.exception("pos_customer_history_failed customer_ref=%s", customer_ref)
        return {}

    favorite = ""
    favorite_item: dict = {}
    last_order_items: list[dict] = []
    counts: dict[str, tuple[str, float, int]] = {}
    if recent:
        for item in recent[0].items or []:
            sku = str(item.get("sku") or "")
            if not sku or sku == "__DELIVERY_FEE__":
                continue
            try:
                qty = int(item.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1
            last_order_items.append({
                "sku": sku,
                "name": str(item.get("name") or sku),
                "qty": max(1, qty),
                "unit_price_q": _int_q(item.get("unit_price_q") or item.get("price_q") or item.get("unit_price") or 0),
            })
    for order in recent:
        for item in order.items or []:
            sku = str(item.get("sku") or "")
            if not sku or sku == "__DELIVERY_FEE__":
                continue
            name = str(item.get("name") or sku)
            try:
                qty = float(item.get("qty") or 1)
            except (TypeError, ValueError):
                qty = 1
            unit_price_q = _int_q(item.get("unit_price_q") or item.get("price_q") or item.get("unit_price") or 0)
            prev_name, prev_qty, prev_price_q = counts.get(sku, (name, 0, unit_price_q))
            counts[sku] = (prev_name or name, prev_qty + qty, prev_price_q or unit_price_q)
    if counts:
        fav_sku, fav_row = max(counts.items(), key=lambda row: row[1][1])
        favorite = fav_row[0]
        favorite_item = {
            "sku": fav_sku,
            "name": fav_row[0],
            "qty": 1,
            "unit_price_q": fav_row[2],
        }

    return {
        "total_orders": stats.total_orders,
        "total_spent_q": stats.total_spent_q,
        "average_order_q": stats.average_order_q,
        "last_order_at": stats.last_order_at,
        "favorite_product": favorite,
        "favorite_item": favorite_item,
        "last_order_items": last_order_items[:8],
    }


def close_sale(
    *,
    channel_ref: str,
    payload: dict,
    actor: str,
    operator_username: str,
) -> PosSaleResult:
    """Create and commit a POS sale from a parsed cart payload."""
    payload = parse_pos_sale_intent(payload, for_commit=True).payload
    validate_manager_approval(payload, operator_username=operator_username)
    _validate_payment_completion(payload)
    channel, config = _channel_and_config(channel_ref)
    session = _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
    if session is None:
        existing = _existing_sale_by_client_request_id(channel_ref=channel.ref, payload=payload)
        if existing is not None:
            return PosSaleResult(order_ref=existing.ref, total_q=existing.total_q, fiscal_hint=_sale_fiscal_hint(existing))
        raise ValueError("Abra um POS tab antes de finalizar.")

    tab_code = _session_tab_code(session)
    fulfillment_type = _payload_fulfillment_type(payload)
    ops = _replace_session_ops(session, payload, operator_username)
    ops.extend([
        {"op": "set_data", "path": "origin_channel", "value": "pos"},
        {"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type},
        {"op": "set_data", "path": "tab_code", "value": tab_code},
        {"op": "set_data", "path": "tab_display", "value": display_tab_code(tab_code)},
        {"op": "set_data", "path": "pos_operator", "value": operator_username},
        {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
    ])
    client_request_id = _payload_client_request_id(payload)
    if client_request_id:
        ops.extend([
            {"op": "set_data", "path": "client_request_id", "value": client_request_id},
            {"op": "set_data", "path": "pos.client_request_id", "value": client_request_id},
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
        idempotency_key=_payload_client_request_id(payload) or session_service.new_idempotency_key(),
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
    order = Order.objects.filter(ref=result.order_ref).first()
    if order is not None:
        order = _reconcile_order_payment_to_total(order)
    return PosSaleResult(
        order_ref=result.order_ref,
        total_q=int(order.total_q if order is not None else result.total_q),
        fiscal_hint=_sale_fiscal_hint(order),
    )


def review_sale(
    *,
    channel_ref: str,
    payload: dict,
    operator_username: str,
) -> PosSaleReview:
    """Validate a POS checkout intent without committing the Orderman session."""
    payload = parse_pos_sale_intent(payload, for_commit=True).payload
    _validate_payment_completion(payload)
    channel, _config = _channel_and_config(channel_ref)
    session = _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
    if session is None:
        raise ValueError("Abra um POS tab antes de finalizar.")

    fulfillment_type = _payload_fulfillment_type(payload)
    payment_collection = _payload_payment_collection(payload, fulfillment_type)
    subtotal_q = _payload_subtotal_q(payload)
    discount_q = _payload_discount_q(payload)
    delivery_fee_q = _payload_delivery_fee_q(payload)
    total_q = _payload_total_q(payload)
    tenders = _payload_tenders(
        payload,
        payment_collection=payment_collection,
        total_q=total_q,
        cash_shift_id=payload.get("cash_shift_id"),
        pos_terminal_ref=str(payload.get("pos_terminal_ref") or "").strip(),
    )
    payment_method = _legacy_payment_method(payload, tenders)
    tender_total_q = sum(_int_q(tender.get("amount_q")) for tender in tenders)
    tendered_amount_q = _int_q(payload.get("tendered_amount_q"))
    threshold_q = _discount_approval_threshold_q()
    warnings: list[dict] = []
    if payment_method == "cash" and payment_collection == "terminal" and tendered_amount_q <= 0:
        warnings.append({
            "code": "cash_tendered_amount_blank",
            "field": "tendered_amount_q",
            "message": "Valor recebido em dinheiro não informado; o fechamento assumirá valor exato.",
        })

    return PosSaleReview(
        intent_version=POS_SALE_INTENT_VERSION,
        tab_code=_session_tab_code(session),
        subtotal_q=subtotal_q,
        discount_q=discount_q,
        delivery_fee_q=delivery_fee_q,
        total_q=total_q,
        payment_method=payment_method,
        payment_collection=payment_collection,
        tender_total_q=tender_total_q,
        tender_count=len(tenders),
        tendered_amount_q=tendered_amount_q,
        change_q=max(0, tendered_amount_q - total_q) if tendered_amount_q else 0,
        requires_manager_approval=threshold_q > 0 and discount_q > threshold_q,
        manager_approval_threshold_q=threshold_q,
        receipt_mode=str(payload.get("receipt_mode") or "none").strip() or "none",
        issue_fiscal_document=bool(payload.get("issue_fiscal_document")),
        warnings=tuple(warnings),
    )


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
    payload = parse_pos_sale_intent(payload, for_commit=False).payload
    channel, config = _channel_and_config(channel_ref)
    session = _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
    if session is None:
        raise ValueError("Abra um POS tab antes de deixar em espera.")

    tab_code = _session_tab_code(session)
    _ensure_pos_tab(tab_code)
    fulfillment_type = _payload_fulfillment_type(payload)
    ops = _replace_session_ops(session, payload, operator_username)
    ops.extend([
        {"op": "set_data", "path": "origin_channel", "value": "pos"},
        {"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type},
        {"op": "set_data", "path": "tab_code", "value": tab_code},
        {"op": "set_data", "path": "tab_display", "value": display_tab_code(tab_code)},
        {"op": "set_data", "path": "pos_operator", "value": operator_username},
        {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
    ])
    client_request_id = _payload_client_request_id(payload)
    if client_request_id:
        ops.extend([
            {"op": "set_data", "path": "client_request_id", "value": client_request_id},
            {"op": "set_data", "path": "pos.client_request_id", "value": client_request_id},
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


def reopen_recent_order_for_correction(
    *,
    order_ref: str,
    actor: str,
    reason: str,
    max_age_minutes: int = 5,
) -> None:
    """Cancel a recent POS order with an explicit correction reason."""
    reason = str(reason or "").strip()
    if not reason:
        raise ValueError("Informe o motivo da correção.")
    cancel_recent_order(
        order_ref=order_ref,
        actor=actor,
        max_age_minutes=max_age_minutes,
    )
    order = Order.objects.filter(ref=order_ref).first()
    if order is None:
        return
    data = dict(order.data or {})
    data["pos_correction_reason"] = reason
    order.data = data
    order.save(update_fields=["data", "updated_at"])


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
    customer_email = str(payload.get("customer_email", "") or "").strip()
    if not customer_email and str(payload.get("receipt_mode") or "").strip() == "email":
        customer_email = str(payload.get("receipt_email", "") or "").strip()
    persisted_customer = _persist_customer_from_payload(payload, operator_username=operator_username)
    if persisted_customer:
        customer_name = customer_name or persisted_customer.get("name", "")
        customer_phone = customer_phone or persisted_customer.get("phone", "")
        customer_tax_id = customer_tax_id or persisted_customer.get("tax_id", "")
        customer_email = customer_email or persisted_customer.get("email", "")

    if customer_name:
        ops.append({"op": "set_data", "path": "customer.name", "value": customer_name})
    if customer_phone:
        ops.append({"op": "set_data", "path": "customer.phone", "value": customer_phone})
    if customer_tax_id:
        ops.append({"op": "set_data", "path": "customer.tax_id", "value": customer_tax_id})
    if customer_email:
        ops.append({"op": "set_data", "path": "customer.email", "value": customer_email})

    if persisted_customer:
        ops.append({"op": "set_data", "path": "customer.ref", "value": persisted_customer["ref"]})
        ops.append({"op": "set_data", "path": "customer_ref", "value": persisted_customer["ref"]})
        if persisted_customer.get("group"):
            ops.append({"op": "set_data", "path": "customer.group", "value": persisted_customer["group"]})
    else:
        customer = resolve_customer(customer_phone)
        if customer:
            ops.append({"op": "set_data", "path": "customer.ref", "value": customer.ref})
            ops.append({"op": "set_data", "path": "customer_ref", "value": customer.ref})
            if customer.group_id:
                ops.append({"op": "set_data", "path": "customer.group", "value": customer.group.ref})

    fulfillment_type = _payload_fulfillment_type(payload)
    ops.append({"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type})
    if fulfillment_type == "delivery":
        _append_delivery_ops(ops, payload)
        delivery_fee_q = _int_q(payload.get("delivery_fee_q"))
        if delivery_fee_q > 0:
            ops.append({
                "op": "add_line",
                "sku": "__DELIVERY_FEE__",
                "name": "Taxa de entrega",
                "qty": 1,
                "unit_price_q": delivery_fee_q,
                "meta": {"type": "delivery_fee", "non_production": True},
            })

    payment_collection = _payload_payment_collection(payload, fulfillment_type)
    total_q = _payload_total_q(payload)

    cash_shift_id = payload.get("cash_shift_id")
    if cash_shift_id:
        ops.append({"op": "set_data", "path": "pos.cash_shift_id", "value": int(cash_shift_id)})
    pos_terminal_ref = str(payload.get("pos_terminal_ref") or "").strip()
    if pos_terminal_ref:
        ops.append({"op": "set_data", "path": "pos.terminal_ref", "value": pos_terminal_ref})
    intent_version = str(payload.get("intent_version") or "").strip()
    if intent_version:
        ops.append({"op": "set_data", "path": "pos.intent_version", "value": intent_version})
    memory_action = str(payload.get("customer_memory_action") or "").strip()
    if memory_action:
        ops.append({"op": "set_data", "path": "pos.customer_memory_action", "value": memory_action})

    tenders = _payload_tenders(
        payload,
        payment_collection=payment_collection,
        total_q=total_q,
        cash_shift_id=cash_shift_id,
        pos_terminal_ref=pos_terminal_ref,
    )
    payment_method = _legacy_payment_method(payload, tenders)
    ops.append({"op": "set_data", "path": "payment.method", "value": payment_method})
    ops.append({"op": "set_data", "path": "payment.collection", "value": payment_collection})
    ops.append({"op": "set_data", "path": "payment.amount_q", "value": total_q})

    tendered_amount_q = payload.get("tendered_amount_q")
    if tendered_amount_q and payment_method == "cash":
        tendered_q = int(tendered_amount_q)
        ops.append({"op": "set_data", "path": "payment.tendered_q", "value": tendered_q})
        ops.append({"op": "set_data", "path": "payment.change_q", "value": max(0, tendered_q - total_q)})
    if tenders:
        ops.append({"op": "set_data", "path": "payment.tenders", "value": tenders})
    cash_received_q = _cash_received_q(tenders)
    if cash_received_q > 0:
        ops.append({"op": "set_data", "path": "payment.cash_received_q", "value": cash_received_q})

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
        approval = payload.get("manager_approval") or {}
        approved_by = str(approval.get("username") or "").strip()
        if approved_by:
            ops.append({"op": "set_data", "path": "manual_discount.approved_by", "value": approved_by})
    return ops


def validate_manager_approval(payload: dict, *, operator_username: str) -> None:
    """Require manager credentials for configured POS discount thresholds."""
    threshold_q = _discount_approval_threshold_q()
    if threshold_q <= 0:
        return
    manual_discount = payload.get("manual_discount") or {}
    try:
        discount_q = int(manual_discount.get("discount_q", 0) or 0)
    except (TypeError, ValueError):
        discount_q = 0
    if discount_q <= threshold_q:
        return

    approval = payload.get("manager_approval") or {}
    username = str(approval.get("username") or "").strip()
    password = str(approval.get("password") or "")
    if not username or not password:
        raise ValueError("Desconto exige aprovação gerencial.")

    from django.contrib.auth import authenticate

    user = authenticate(username=username, password=password)
    if not user or not user.is_active or not user.has_perm("backstage.adjust_cashshift"):
        raise ValueError("Aprovação gerencial inválida.")
    logger.info(
        "pos_manager_approval operator=%s approved_by=%s discount_q=%s",
        operator_username,
        username,
        discount_q,
    )


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
        {"op": "set_data", "path": "client_request_id", "value": ""},
        {"op": "set_data", "path": "pos.client_request_id", "value": ""},
        {"op": "set_data", "path": "delivery_address", "value": ""},
        {"op": "set_data", "path": "delivery_address_structured", "value": {}},
        {"op": "set_data", "path": "delivery_date", "value": ""},
        {"op": "set_data", "path": "delivery_time_slot", "value": ""},
        {"op": "set_data", "path": "delivery_fee_q", "value": 0},
        {"op": "set_data", "path": "order_notes", "value": ""},
    ])
    ops.extend(build_session_ops(payload, operator_username))
    return ops


def _payload_fulfillment_type(payload: dict) -> str:
    value = str(payload.get("fulfillment_type") or "pickup").strip().lower()
    if value == "delivery":
        return "delivery"
    return "pickup"


def _payload_payment_collection(payload: dict, fulfillment_type: str) -> str:
    value = str(payload.get("payment_collection") or "terminal").strip().lower()
    if fulfillment_type == "delivery" and value == "on_delivery":
        return "on_delivery"
    return "terminal"


def _payload_total_q(payload: dict) -> int:
    return max(0, _payload_subtotal_q(payload) - _payload_discount_q(payload) + _payload_delivery_fee_q(payload))


def _payload_subtotal_q(payload: dict) -> int:
    subtotal_q = 0
    for item in payload.get("items", []):
        try:
            subtotal_q += int(item.get("qty", 1)) * int(item.get("unit_price_q", 0))
        except (TypeError, ValueError):
            continue
    return max(0, subtotal_q)


def _payload_discount_q(payload: dict) -> int:
    manual_discount = payload.get("manual_discount") or {}
    try:
        return max(0, int(manual_discount.get("discount_q", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _payload_delivery_fee_q(payload: dict) -> int:
    try:
        return max(0, int(payload.get("delivery_fee_q", 0) or 0))
    except (TypeError, ValueError):
        return 0


def _validate_payment_completion(payload: dict) -> None:
    total_q = _payload_total_q(payload)
    fulfillment_type = _payload_fulfillment_type(payload)
    payment_collection = _payload_payment_collection(payload, fulfillment_type)
    tenders = _payload_tenders(
        payload,
        payment_collection=payment_collection,
        total_q=total_q,
        cash_shift_id=payload.get("cash_shift_id"),
        pos_terminal_ref=str(payload.get("pos_terminal_ref") or "").strip(),
    )
    payment_method = _legacy_payment_method(payload, tenders)
    tendered_q = _int_q(payload.get("tendered_amount_q"))
    if payment_method == "cash" and payment_collection == "terminal" and tendered_q and tendered_q < total_q:
        raise PosIntentError(
            code="cash_tendered_amount_too_low",
            message="Valor recebido em dinheiro menor que o total da venda.",
            field="tendered_amount_q",
            focus="payment",
            recovery="Informe o valor recebido ou use dinheiro exato.",
        )


def _discount_approval_threshold_q() -> int:
    return max(0, int(getattr(settings, "SHOPMAN_POS_DISCOUNT_APPROVAL_THRESHOLD_Q", 0) or 0))


def _payload_tenders(
    payload: dict,
    *,
    payment_collection: str,
    total_q: int,
    cash_shift_id,
    pos_terminal_ref: str,
) -> list[dict]:
    raw = payload.get("payment_tenders")
    if isinstance(raw, list) and raw:
        tenders = []
        for tender in raw:
            method = _normalize_payment_method(tender.get("method"))
            try:
                amount_q = int(tender.get("amount_q") or 0)
            except (TypeError, ValueError):
                amount_q = 0
            if amount_q <= 0:
                continue
            collection = str(tender.get("collection") or payment_collection).strip().lower()
            if collection not in {"terminal", "on_delivery"}:
                collection = payment_collection
            entry = {
                "method": method,
                "amount_q": amount_q,
                "collection": collection,
                "status": "pending" if collection == "on_delivery" else "received",
            }
            reference = str(tender.get("reference") or "").strip()
            if reference:
                entry["reference"] = reference[:120]
            if cash_shift_id and entry["collection"] == "terminal":
                entry["cash_shift_id"] = int(cash_shift_id)
            if pos_terminal_ref and entry["collection"] == "terminal":
                entry["terminal_ref"] = pos_terminal_ref
            if entry["collection"] == "terminal":
                entry["received_at"] = timezone.now().isoformat()
            tenders.append(entry)
        paid_q = sum(int(tender["amount_q"]) for tender in tenders)
        if total_q > 0 and paid_q != total_q:
            raise ValueError("Pagamentos informados não fecham o total da venda.")
        return tenders

    if total_q <= 0:
        return []
    payment_method = _normalize_payment_method(payload.get("payment_method") or "cash")
    tender = {
        "method": payment_method,
        "amount_q": total_q,
        "collection": payment_collection,
        "status": "pending" if payment_collection == "on_delivery" else "received",
    }
    if cash_shift_id and payment_collection == "terminal":
        tender["cash_shift_id"] = int(cash_shift_id)
    if pos_terminal_ref and payment_collection == "terminal":
        tender["terminal_ref"] = pos_terminal_ref
    if payment_collection == "terminal":
        tender["received_at"] = timezone.now().isoformat()
    return [tender]


def _legacy_payment_method(payload: dict, tenders: list[dict]) -> str:
    methods = {str(tender.get("method") or "").strip() for tender in tenders if tender.get("amount_q")}
    methods.discard("")
    if len(methods) > 1:
        return "mixed"
    if len(methods) == 1:
        return next(iter(methods))
    return _normalize_payment_method(payload.get("payment_method") or "cash")


def _normalize_payment_method(value) -> str:
    method = str(value or "cash").strip().lower() or "cash"
    if method in {"cash", "pix", "card", "external", "mixed"}:
        return method
    return "external"


def _cash_received_q(tenders: list[dict]) -> int:
    total = 0
    for tender in tenders:
        if tender.get("method") != "cash":
            continue
        if tender.get("collection", "terminal") != "terminal":
            continue
        if tender.get("status") not in {"received", "captured", "paid", ""}:
            continue
        total += int(tender.get("amount_q") or 0)
    return total


def _reconcile_order_payment_to_total(order: Order) -> Order:
    """Align POS payment metadata with the final committed Orderman total."""
    final_total_q = int(order.total_q or 0)
    data = dict(order.data or {})
    payment = dict(data.get("payment") or {})
    if not payment:
        return order

    original_amount_q = _int_q(payment.get("amount_q"))
    tenders = [dict(tender) for tender in payment.get("tenders") or [] if isinstance(tender, dict)]
    original_tender_total_q = sum(_int_q(tender.get("amount_q")) for tender in tenders)
    if original_amount_q == final_total_q and (not tenders or original_tender_total_q == final_total_q):
        return order

    payment["amount_q"] = final_total_q
    if original_amount_q != final_total_q:
        payment["pos_reconciled_from_amount_q"] = original_amount_q

    if tenders:
        _reconcile_tenders_to_total(tenders, final_total_q)
        payment["tenders"] = tenders
        cash_received_q = _cash_received_q(tenders)
        if cash_received_q > 0:
            payment["cash_received_q"] = cash_received_q
        else:
            payment.pop("cash_received_q", None)

    tendered_q = _int_q(payment.get("tendered_q"))
    if tendered_q > 0:
        payment["change_q"] = max(0, tendered_q - final_total_q)

    data["payment"] = payment
    order.data = data
    order.save(update_fields=["data", "updated_at"])
    return order


def _reconcile_tenders_to_total(tenders: list[dict], final_total_q: int) -> None:
    if not tenders:
        return
    if len(tenders) == 1:
        tenders[0]["amount_q"] = final_total_q
        return

    remaining_delta_q = final_total_q - sum(_int_q(tender.get("amount_q")) for tender in tenders)
    for tender in reversed(tenders):
        if remaining_delta_q == 0:
            return
        current_q = _int_q(tender.get("amount_q"))
        next_q = max(0, current_q + remaining_delta_q)
        tender["amount_q"] = next_q
        remaining_delta_q -= next_q - current_q


def _int_q(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _append_delivery_ops(ops: list[dict], payload: dict) -> None:
    structured_address = payload.get("delivery_address_structured") if isinstance(payload.get("delivery_address_structured"), dict) else {}
    address = str(payload.get("delivery_address") or structured_address.get("formatted_address") or "").strip()
    if address:
        ops.append({"op": "set_data", "path": "delivery_address", "value": address})
    structured = payload.get("delivery_address_structured") or {}
    if isinstance(structured, dict) and structured:
        ops.append({"op": "set_data", "path": "delivery_address_structured", "value": structured})
    delivery_date = str(payload.get("delivery_date") or "").strip()
    if delivery_date:
        ops.append({"op": "set_data", "path": "delivery_date", "value": delivery_date})
    delivery_time_slot = str(payload.get("delivery_time_slot") or "").strip()
    if delivery_time_slot:
        ops.append({"op": "set_data", "path": "delivery_time_slot", "value": delivery_time_slot})
    order_notes = str(payload.get("order_notes") or "").strip()
    if order_notes:
        ops.append({"op": "set_data", "path": "order_notes", "value": order_notes})
    try:
        delivery_fee_q = int(payload.get("delivery_fee_q") or 0)
    except (TypeError, ValueError):
        delivery_fee_q = 0
    if delivery_fee_q > 0:
        ops.append({"op": "set_data", "path": "delivery_fee_q", "value": delivery_fee_q})


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
        if not _is_delivery_fee_item(item)
    ]

    return {
        "session_key": session.session_key,
        "tab_session_key": session.session_key,
        "tab_code": tab_code,
        "tab_display": display_tab_code(tab_code),
        "items": items,
        "customer_phone": customer.get("phone", ""),
        "customer_name": customer.get("name", ""),
        "customer_ref": customer.get("ref", data.get("customer_ref", "")),
        "customer_group": customer.get("group", ""),
        "customer_tax_id": customer.get("tax_id", ""),
        "customer_email": customer.get("email", ""),
        "fulfillment_type": data.get("fulfillment_type", "pickup") or "pickup",
        "delivery_address": data.get("delivery_address", ""),
        "delivery_address_structured": data.get("delivery_address_structured", {}),
        "delivery_date": data.get("delivery_date", ""),
        "delivery_time_slot": data.get("delivery_time_slot", ""),
        "delivery_fee_q": data.get("delivery_fee_q", 0),
        "order_notes": data.get("order_notes", ""),
        "payment_method": payment.get("method", "cash"),
        "payment_collection": payment.get("collection", "terminal"),
        "payment_tenders": payment.get("tenders", []),
        "tendered_amount_q": payment.get("tendered_q", ""),
        "client_request_id": data.get("client_request_id", (data.get("pos") or {}).get("client_request_id", "")),
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
    session_pos_data = dict(session_data.get("pos") or {})
    if session_pos_data:
        order_data["pos"] = {**dict(order_data.get("pos") or {}), **session_pos_data}
    client_request_id = session_data.get("client_request_id") or (session_data.get("pos") or {}).get("client_request_id")
    if client_request_id:
        order_data["client_request_id"] = client_request_id
        pos_data = dict(order_data.get("pos") or {})
        pos_data["client_request_id"] = client_request_id
        order_data["pos"] = pos_data
    if order_data.get("fulfillment_type") != "delivery":
        for key in ("delivery_address", "delivery_address_structured", "delivery_date", "delivery_time_slot", "delivery_fee_q"):
            order_data.pop(key, None)

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


def _payload_client_request_id(payload: dict) -> str:
    raw = str(payload.get("client_request_id") or "").strip()
    if not raw:
        return ""
    safe = "".join(ch for ch in raw if ch.isalnum() or ch in "-_:")
    if safe != raw or len(safe) > 128:
        return ""
    return safe


def _is_delivery_fee_item(item: dict) -> bool:
    meta = item.get("meta") or {}
    return item.get("sku") == "__DELIVERY_FEE__" or meta.get("type") == "delivery_fee"


def _existing_sale_by_client_request_id(*, channel_ref: str, payload: dict) -> Order | None:
    key = _payload_client_request_id(payload)
    if not key:
        return None
    return (
        Order.objects.filter(channel_ref=channel_ref)
        .filter(Q(data__client_request_id=key) | Q(data__pos__client_request_id=key))
        .order_by("-created_at")
        .first()
    )


def _sale_fiscal_hint(order: Order | None) -> str:
    if order is None:
        return ""
    if ((order.data or {}).get("fiscal") or {}).get("issue_document"):
        return " · Fiscal pendente"
    return ""


def _persist_customer_from_payload(payload: dict, *, operator_username: str) -> dict:
    """Resolve/create/update a Guestman customer from any POS customer data."""
    name = str(payload.get("customer_name") or "").strip()
    phone = _normalize_phone(str(payload.get("customer_phone") or "").strip())
    tax_id = _digits(str(payload.get("customer_tax_id") or "").strip())
    email = str(payload.get("customer_email") or "").strip().lower()
    if not email and str(payload.get("receipt_mode") or "").strip() == "email":
        email = str(payload.get("receipt_email") or "").strip().lower()
    structured_address = payload.get("delivery_address_structured") if isinstance(payload.get("delivery_address_structured"), dict) else {}
    address = str(payload.get("delivery_address") or structured_address.get("formatted_address") or "").strip()
    raw_ref = str(payload.get("customer_ref") or "").strip()

    if not any((raw_ref, name, phone, tax_id, email, address)):
        return {}

    try:
        from shopman.guestman.models import ContactPoint, Customer
        from shopman.guestman.services import address as address_service
    except ImportError:
        logger.warning("pos_customer_persist_skipped_guestman_unavailable")
        return {}

    with transaction.atomic():
        customer = _resolve_pos_customer(
            Customer,
            ref=raw_ref,
            phone=phone,
            tax_id=tax_id,
            email=email,
        )
        if customer is None:
            first_name, last_name = _split_name(name)
            fallback = _fallback_customer_name(phone=phone, tax_id=tax_id, email=email)
            customer = Customer.objects.create(
                ref=Customer.generate_ref(),
                first_name=first_name or fallback[0],
                last_name=last_name or fallback[1],
                phone=phone,
                email=email,
                document=tax_id,
                source_system="pdv",
                created_by=operator_username,
                metadata={
                    "pos": {
                        "created_from_pos": True,
                        "first_operator": operator_username,
                        "captured_at": timezone.now().isoformat(),
                    }
                },
            )
        else:
            _merge_pos_customer_fields(
                customer,
                name=name,
                phone=phone,
                tax_id=tax_id,
                email=email,
                operator_username=operator_username,
            )

        if phone:
            _ensure_contact_point(ContactPoint, customer, ContactPoint.Type.PHONE, phone)
        if email:
            _ensure_contact_point(ContactPoint, customer, ContactPoint.Type.EMAIL, email)
        if tax_id:
            _ensure_customer_identifier(customer.ref, "cpf", tax_id)
        if address:
            _ensure_customer_address(address_service, customer.ref, address, structured_address)

        customer.refresh_from_db()
        return {
            "ref": customer.ref,
            "name": customer.name,
            "phone": customer.phone,
            "tax_id": customer.document,
            "email": customer.email,
            "group": customer.group.ref if customer.group_id else "",
        }


def _resolve_pos_customer(Customer, *, ref: str, phone: str, tax_id: str, email: str):
    candidates: dict[int, object] = {}
    evidence: dict[int, set[str]] = {}

    def add(candidate, source: str) -> None:
        if candidate is None:
            return
        candidates[candidate.pk] = candidate
        evidence.setdefault(candidate.pk, set()).add(source)

    if ref:
        add(Customer.objects.filter(ref=ref, is_active=True).first(), "ref")
    if phone:
        from shopman.guestman.services import customer as customer_service

        add(customer_service.get_by_phone(phone), "phone")
    if tax_id:
        from shopman.guestman.services import customer as customer_service

        add(customer_service.get_by_document(tax_id), "document")
        add(_find_customer_identifier("cpf", tax_id), "cpf")
    if email:
        from shopman.guestman.services import customer as customer_service

        add(customer_service.get_by_email(email), "email")

    if not candidates:
        return None
    if len(candidates) == 1:
        return next(iter(candidates.values()))

    detail = ", ".join(
        f"{getattr(customer, 'ref', customer_id)} via {'/'.join(sorted(evidence.get(customer_id, ())))}"
        for customer_id, customer in candidates.items()
    )
    raise ValueError(
        "Dados do cliente apontam para cadastros diferentes. "
        f"Revise telefone, CPF/CNPJ ou e-mail antes de fechar. ({detail})"
    )


def _merge_pos_customer_fields(
    customer,
    *,
    name: str,
    phone: str,
    tax_id: str,
    email: str,
    operator_username: str,
) -> None:
    first_name, last_name = _split_name(name)
    updates: list[str] = []

    if first_name and _should_refresh_name(customer):
        customer.first_name = first_name
        updates.append("first_name")
        if last_name:
            customer.last_name = last_name
            updates.append("last_name")
    elif last_name and not customer.last_name:
        customer.last_name = last_name
        updates.append("last_name")

    if phone and not customer.phone:
        customer.phone = phone
        updates.append("phone")
    if email and not customer.email:
        customer.email = email
        updates.append("email")
    if tax_id and not customer.document:
        customer.document = tax_id
        updates.append("document")

    metadata = dict(customer.metadata or {})
    pos_meta = dict(metadata.get("pos") or {})
    pos_meta.update({
        "last_operator": operator_username,
        "last_capture_at": timezone.now().isoformat(),
    })
    captured = sorted(k for k, v in {
        "name": name,
        "phone": phone,
        "tax_id": tax_id,
        "email": email,
    }.items() if v)
    if captured:
        pos_meta["last_captured_fields"] = captured
    metadata["pos"] = pos_meta
    if metadata != (customer.metadata or {}):
        customer.metadata = metadata
        updates.append("metadata")

    if updates:
        customer.save(update_fields=sorted(set(updates + ["updated_at"])))


def _ensure_contact_point(ContactPoint, customer, contact_type: str, value: str) -> None:
    try:
        contact, created = ContactPoint.objects.get_or_create(
            type=contact_type,
            value_normalized=value,
            defaults={
                "customer": customer,
                "value_display": value,
                "is_primary": not ContactPoint.objects.filter(customer=customer, type=contact_type).exists(),
            },
        )
    except IntegrityError as exc:
        raise ValueError("Contato já pertence a outro cliente.") from exc
    if contact.customer_id != customer.pk:
        raise ValueError("Contato já pertence a outro cliente.")
    if created and contact.is_primary:
        contact._sync_to_customer()


def _ensure_customer_identifier(customer_ref: str, identifier_type: str, identifier_value: str) -> None:
    try:
        from shopman.guestman.contrib.identifiers import IdentifierService

        IdentifierService.ensure_identifier(
            customer_ref=customer_ref,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            is_primary=True,
            source_system="pdv",
        )
    except ValueError as exc:
        raise ValueError("Identificador fiscal já pertence a outro cliente.") from exc


def _find_customer_identifier(identifier_type: str, identifier_value: str):
    try:
        from shopman.guestman.contrib.identifiers import IdentifierService

        return IdentifierService.find_by_identifier(identifier_type, identifier_value)
    except Exception:
        logger.debug("pos_customer_identifier_lookup_failed type=%s", identifier_type, exc_info=True)
        return None


def _ensure_customer_address(address_service, customer_ref: str, formatted_address: str, structured: dict | None = None) -> None:
    structured = structured if isinstance(structured, dict) else {}
    place_id = str(structured.get("place_id") or "").strip()
    existing = address_service.find_by_place_id(customer_ref, place_id) if place_id else None
    if existing is None and address_service.has_address(customer_ref, formatted_address):
        return

    components = {
        key: str(structured.get(key) or "").strip()
        for key in (
            "route",
            "street_number",
            "neighborhood",
            "city",
            "state",
            "state_code",
            "postal_code",
            "country",
            "country_code",
        )
        if str(structured.get(key) or "").strip()
    }
    coordinates = _structured_coordinates(structured)
    complement = str(structured.get("complement") or "").strip()
    delivery_instructions = str(structured.get("delivery_instructions") or structured.get("reference") or "").strip()

    if existing is not None:
        updates = {
            "formatted_address": formatted_address,
            "place_id": place_id,
            **components,
        }
        if complement:
            updates["complement"] = complement
        if delivery_instructions:
            updates["delivery_instructions"] = delivery_instructions
        if coordinates:
            updates["latitude"] = coordinates[0]
            updates["longitude"] = coordinates[1]
        address_service.update_address(customer_ref, existing.id, **updates)
        return

    address_service.add_address(
        customer_ref=customer_ref,
        label="home",
        formatted_address=formatted_address,
        place_id=place_id or None,
        components=components,
        coordinates=coordinates,
        complement=complement,
        delivery_instructions=delivery_instructions,
        is_default=not address_service.has_any_address(customer_ref),
    )


def _structured_coordinates(structured: dict) -> tuple[float, float] | None:
    try:
        lat = float(structured.get("latitude"))
        lng = float(structured.get("longitude"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return lat, lng


def _split_name(full_name: str) -> tuple[str, str]:
    parts = full_name.strip().split(None, 1)
    return (parts[0] if parts else "", parts[1] if len(parts) > 1 else "")


def _fallback_customer_name(*, phone: str, tax_id: str, email: str) -> tuple[str, str]:
    if phone:
        return "Cliente", phone[-4:]
    if tax_id:
        return "Cliente", f"Doc {tax_id[-4:]}"
    if email:
        return "Cliente", email.split("@", 1)[0][:40]
    return "Cliente", "POS"


def _should_refresh_name(customer) -> bool:
    current = f"{customer.first_name} {customer.last_name}".strip().lower()
    return not current or current.startswith("cliente ") or current == "cliente"


def _normalize_phone(value: str) -> str:
    if not value:
        return ""
    try:
        from shopman.utils.phone import normalize_phone

        return normalize_phone(value)
    except Exception:
        logger.debug("pos_phone_normalization_failed", exc_info=True)
        return value


def _digits(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _channel_and_config(channel_ref: str) -> tuple[Channel, ChannelConfig]:
    try:
        channel = Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist as exc:
        raise ValueError(f"Canal {channel_ref} não configurado. Contacte o suporte.") from exc
    return channel, ChannelConfig.for_channel(channel)
