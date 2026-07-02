"""POS mutation facade.

Backstage POS views own permissions, HTTP parsing, and HTML responses. This
module owns the Orderman session writes and POS order mutations.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from shopman.orderman.models import Order, Session
from shopman.utils.monetary import format_money

from shopman.shop.adapters import pos as pos_adapter
from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel
from shopman.shop.services import payment as payment_service
from shopman.shop.services import sessions as session_service
from shopman.shop.services.cancellation import cancel
from shopman.shop.services.pos_intent import POS_SALE_INTENT_VERSION, PosIntentError, parse_pos_sale_intent

logger = logging.getLogger(__name__)

_TAB_REF_MAX_LENGTH = 64
_TAB_REF_DISALLOWED = set('/\\?#%\r\n\t')


@dataclass(frozen=True)
class PosSaleResult:
    order_ref: str
    total_q: int
    fiscal_hint: str = ""
    payment: dict | None = None


@dataclass(frozen=True)
class PosSaleReview:
    intent_version: str
    tab_ref: str
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
    tab_ref: str
    tab_display: str
    session_key: str


@dataclass(frozen=True)
class PosMoveResult:
    """Outcome of a move-lines command (transfer/split/merge).

    Carries the mutated sessions; the surface reads each comanda's payload via
    the projection. ``source`` is ``None`` when the emptied source was closed.
    """

    target: Session
    source: Session | None
    source_closed: bool


@dataclass(frozen=True)
class PosFireResult:
    """Outcome of a fire-to-kitchen command: the mutated session + effects."""

    session: Session
    fired_count: int
    fired_lines: tuple[str, ...]


@dataclass(frozen=True)
class PosUnfireResult:
    """Outcome of a cancel-fire command: the mutated session + effects."""

    session: Session
    cancelled: int
    trimmed: int
    fired_lines: tuple[str, ...]


def normalize_tab_ref(value: str) -> str:
    """Normalize a POS tab reference.

    Numeric references keep the legacy 8-digit storage shape. Text references
    are accepted as operator-facing identifiers and normalized to uppercase for
    stable lookup across surfaces.
    """
    raw = _clean_tab_ref(value)
    if raw.isdigit() and len(raw) <= 8:
        return raw.zfill(8)
    return raw.upper()


def display_tab_ref(tab_ref: str) -> str:
    value = str(tab_ref or "").strip()
    if value.isdigit():
        return value.lstrip("0") or "0"
    return value


def _clean_tab_ref(value: str) -> str:
    raw = re.sub(r"\s+", " ", str(value or "").strip())
    if not raw:
        raise ValueError("Informe uma referência de comanda.")
    if len(raw) > _TAB_REF_MAX_LENGTH:
        raise ValueError(f"Informe uma comanda com até {_TAB_REF_MAX_LENGTH} caracteres.")
    if any(ch in _TAB_REF_DISALLOWED or ord(ch) < 32 for ch in raw):
        raise ValueError("A referência da comanda não pode conter barras ou caracteres de URL.")
    return raw


def _tab_label_from_input(value: str, ref: str) -> str:
    try:
        raw = _clean_tab_ref(value)
    except ValueError:
        return display_tab_ref(ref)
    if raw.isdigit() and len(raw) <= 8:
        return display_tab_ref(ref)
    return raw


def register_pos_tab(*, tab_ref: str, label: str = "") -> dict:
    """Register or reactivate a POS tab without opening a sale session."""
    ref = normalize_tab_ref(tab_ref)
    display = _tab_label_from_input(tab_ref, ref)
    label = str(label or "").strip() or display
    return pos_adapter.upsert_tab(ref=ref, label=label, display=display)


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


# ----------------------------------------------------------------- audit trail
# Anti-fraud trail of session-phase actions, emitted by this orchestration layer
# (the kernel SessionEvent stays vocabulary-free). Anchored on session_key, so it
# is durable (survives clear/delete) and continuous into the Order (same key);
# post-commit actions like cancellation are covered by OrderEvent.


def _audit_qty(item: dict):
    try:
        qty = Decimal(str(item.get("qty", 0)))
    except (InvalidOperation, TypeError):
        return 0
    return int(qty) if qty == qty.to_integral_value() else float(qty)


def _audit_item_index(items: list[dict]) -> dict:
    # Key by SKU (stable operator-meaningful identity), not line_id — line_ids are
    # reassigned on reload/persist and would produce false add/remove churn.
    index: dict = {}
    for item in items or []:
        if _is_delivery_fee_item(item):
            continue
        index[str(item.get("sku") or "")] = item
    return index


def _audit_line_diff(session: Session, *, before: list[dict], after: list[dict], actor: str) -> None:
    """Emit add/remove/qty events for the net change between two item snapshots."""
    old = _audit_item_index(before)
    new = _audit_item_index(after)
    for key, item in new.items():
        if key not in old:
            session.emit_event("line_added", actor=actor, payload={
                "sku": item.get("sku"), "name": item.get("name"), "qty": _audit_qty(item),
            })
        elif _audit_qty(item) != _audit_qty(old[key]):
            session.emit_event("qty_changed", actor=actor, payload={
                "sku": item.get("sku"), "name": item.get("name"),
                "qty_before": _audit_qty(old[key]), "qty_after": _audit_qty(item),
            })
    for key, item in old.items():
        if key not in new:
            session.emit_event("line_removed", actor=actor, payload={
                "sku": item.get("sku"), "name": item.get("name"), "qty": _audit_qty(item),
            })


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
    existing = _existing_sale_by_client_request_id(channel_ref=channel.ref, payload=payload)
    if existing is not None and session is None:
        return PosSaleResult(order_ref=existing.ref, total_q=existing.total_q, fiscal_hint=_sale_fiscal_hint(existing))
    if session is None:
        if _payload_has_tab_identity(payload):
            raise ValueError("Abra um POS tab antes de finalizar.")
        session = _create_direct_checkout_session(
            channel_ref=channel.ref,
            payload=payload,
            operator_username=operator_username,
        )
        direct_checkout = True
    else:
        direct_checkout = False

    tab_ref = "" if direct_checkout else _session_tab_ref(session)
    tab_display = "" if direct_checkout else _session_tab_display(session)
    fulfillment_type = _payload_fulfillment_type(payload)
    ops = _replace_session_ops(session, payload, operator_username)
    ops.extend([
        {"op": "set_data", "path": "origin_channel", "value": "pos"},
        {"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type},
        {"op": "set_data", "path": "pos_operator", "value": operator_username},
        {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
    ])
    if direct_checkout:
        ops.append({"op": "set_data", "path": "pos.direct_checkout", "value": True})
    else:
        ops.extend([
            {"op": "set_data", "path": "tab_ref", "value": tab_ref},
            {"op": "set_data", "path": "tab_display", "value": tab_display},
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
        tab_ref=tab_ref,
        operator_username=operator_username,
        session_data=session.data,
    )
    # Transition marker on the session trail; the same session_key now resolves
    # to the Order, whose own lifecycle is audited by OrderEvent.
    session.emit_event("sale_committed", actor=operator_username, payload={
        "order_ref": result.order_ref, "total_q": int(result.total_q),
    })
    logger.info("pos_close_tab order=%s tab=%s session=%s total=%s", result.order_ref, tab_ref, session.session_key, result.total_q)
    order = Order.objects.filter(ref=result.order_ref).first()
    payment_result = {}
    if order is not None:
        order = _reconcile_order_payment_to_total(order)
        payment_result = _maybe_initiate_pos_gateway_payment(order)
    return PosSaleResult(
        order_ref=result.order_ref,
        total_q=int(order.total_q if order is not None else result.total_q),
        fiscal_hint=_sale_fiscal_hint(order),
        payment=payment_result,
    )


def review_sale(
    *,
    channel_ref: str,
    payload: dict,
    operator_username: str,
) -> PosSaleReview:
    """Validate a POS checkout intent without committing the Orderman session."""
    payload = parse_pos_sale_intent(payload, for_commit=True).payload
    channel, _config = _channel_and_config(channel_ref)
    session = _payload_open_tab_session(channel_ref=channel.ref, payload=payload)
    if session is None and _payload_has_tab_identity(payload):
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
        require_complete=False,
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
    if payment_method == "cash" and payment_collection == "terminal" and 0 < tendered_amount_q < total_q:
        warnings.append({
            "code": "cash_tendered_amount_too_low",
            "field": "tendered_amount_q",
            "message": "Valor recebido em dinheiro menor que o total da venda.",
        })
    if payment_method == "mixed" and total_q > 0 and tender_total_q <= 0:
        warnings.append({
            "code": "payment_tenders_required",
            "field": "payment_tenders",
            "message": "Adicione as linhas do pagamento misto antes de finalizar.",
        })
    elif payment_method == "mixed" and total_q > 0 and tender_total_q < total_q:
        warnings.append({
            "code": "payment_tenders_total_mismatch",
            "field": "payment_tenders",
            "message": "Os pagamentos informados não cobrem o total da venda.",
        })

    return PosSaleReview(
        intent_version=POS_SALE_INTENT_VERSION,
        tab_ref=_session_tab_ref(session) if session is not None else "",
        subtotal_q=subtotal_q,
        discount_q=discount_q,
        delivery_fee_q=delivery_fee_q,
        total_q=total_q,
        payment_method=payment_method,
        payment_collection=payment_collection,
        tender_total_q=tender_total_q,
        tender_count=len(tenders),
        tendered_amount_q=tendered_amount_q,
        # Troco: no pagamento misto, o excedente das linhas é o troco (uma linha de
        # dinheiro pode ser recebida a mais); no dinheiro simples, vem do valor recebido.
        change_q=(
            max(0, tender_total_q - total_q)
            if payment_method == "mixed"
            else (max(0, tendered_amount_q - total_q) if tendered_amount_q else 0)
        ),
        requires_manager_approval=(
            (threshold_q > 0 and discount_q > threshold_q)
            or _payload_has_d1_line_discount(payload)
            or _payload_has_price_override(payload)
        ),
        manager_approval_threshold_q=threshold_q,
        receipt_mode=str(payload.get("receipt_mode") or "none").strip() or "none",
        issue_fiscal_document=bool(payload.get("issue_fiscal_document")),
        warnings=tuple(warnings),
    )


def open_pos_tab(
    *,
    channel_ref: str,
    tab_ref: str,
    actor: str,
    operator_username: str,
) -> Session:
    """Open or load the current order for a POS tab (returns the open session)."""
    channel, config = _channel_and_config(channel_ref)
    ref = normalize_tab_ref(tab_ref)
    tab_display = _ensure_pos_tab(ref, display=_tab_label_from_input(tab_ref, ref))
    session = _get_open_pos_tab_session(channel_ref=channel.ref, tab_ref=ref)
    if session is None:
        session = session_service.create_session(
            channel.ref,
            handle_type="pos_tab",
            handle_ref=ref,
            data={
                "origin_channel": "pos",
                "fulfillment_type": "pickup",
                "tab_ref": ref,
                "tab_display": tab_display,
                "pos_operator": operator_username,
                "last_touched_at": timezone.now().isoformat(),
            },
        )
    else:
        session_service.assign_handle(
            session_key=session.session_key,
            channel_ref=channel.ref,
            handle_type="pos_tab",
            handle_ref=ref,
        )
        session_service.modify_session(
            session_key=session.session_key,
            channel_ref=channel.ref,
            ops=[
                {"op": "set_data", "path": "tab_ref", "value": ref},
                {"op": "set_data", "path": "tab_display", "value": tab_display},
                {"op": "set_data", "path": "pos_operator", "value": operator_username},
                {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
            ],
            ctx={"actor": actor},
            channel_config=config.to_dict(),
        )
        session.refresh_from_db()

    logger.info("pos_open_tab tab=%s session=%s operator=%s", ref, session.session_key, operator_username)
    return session


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

    before_items = session.items
    tab_ref = _session_tab_ref(session)
    tab_display = _ensure_pos_tab(tab_ref, display=_session_tab_display(session))
    fulfillment_type = _payload_fulfillment_type(payload)
    ops = _replace_session_ops(session, payload, operator_username)
    ops.extend([
        {"op": "set_data", "path": "origin_channel", "value": "pos"},
        {"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type},
        {"op": "set_data", "path": "tab_ref", "value": tab_ref},
        {"op": "set_data", "path": "tab_display", "value": tab_display},
        {"op": "set_data", "path": "pos_operator", "value": operator_username},
        {"op": "set_data", "path": "last_touched_at", "value": timezone.now().isoformat()},
    ])
    client_request_id = _payload_client_request_id(payload)
    if client_request_id:
        ops.extend([
            {"op": "set_data", "path": "client_request_id", "value": client_request_id},
            {"op": "set_data", "path": "pos.client_request_id", "value": client_request_id},
        ])

    with transaction.atomic():
        session_service.modify_session(
            session_key=session.session_key,
            channel_ref=channel.ref,
            ops=ops,
            ctx={"actor": actor},
            channel_config=config.to_dict(),
        )
        # Audit the net change vs the previously-saved snapshot (catches
        # "saved with N items, later saved with fewer"). Emitted atomically.
        _audit_line_diff(session, before=before_items, after=payload.get("items", []), actor=operator_username)
    logger.info("pos_save_tab tab=%s session=%s operator=%s", tab_ref, session.session_key, operator_username)
    return PosTabResult(tab_ref=tab_ref, tab_display=tab_display, session_key=session.session_key)


def clear_pos_tab(*, channel_ref: str, session_key: str, operator_username: str) -> bool:
    """Abandon the open POS tab session, making the tab empty again."""
    session = _get_open_pos_tab_session_by_key(channel_ref=channel_ref, session_key=session_key)
    if session is None:
        return False
    discarded = [
        {"sku": i.get("sku"), "name": i.get("name"), "qty": _audit_qty(i)}
        for i in session.items if not _is_delivery_fee_item(i)
    ]
    fired = bool((session.data or {}).get("fired_lines"))
    with transaction.atomic():
        # Audit BEFORE abandoning: record what was on the tab when discarded.
        # A tab that was fired to the kitchen and then cleared without a sale is
        # the canonical anti-fraud red flag.
        session.emit_event("tab_cleared", actor=operator_username, payload={
            "items": discarded, "item_count": len(discarded), "was_fired": fired,
        })
        cleared = session_service.abandon_session(session_key=session.session_key, channel_ref=channel_ref)
        if cleared and fired:
            # A cozinha não pode continuar produzindo uma comanda descartada.
            from shopman.shop.adapters import kds as kds_adapter

            cancelled = kds_adapter.cancel_open_tickets_for_session(session.session_key)
            if cancelled:
                logger.info(
                    "pos_clear_tab: %d ticket(s) de cozinha cancelados session=%s",
                    cancelled, session.session_key,
                )
    if cleared:
        logger.info("pos_clear_tab tab=%s session=%s operator=%s", _session_tab_ref(session), session.session_key, operator_username)
    return cleared


def rename_pos_tab(
    *,
    channel_ref: str,
    session_key: str,
    new_tab_ref: str,
    actor: str,
    operator_username: str,
) -> Session:
    """Rename an open comanda's handle (e.g. ``Mesa 5`` → ``João``).

    Respects the open-session handle uniqueness constraint
    (``ord_uniq_open_session_handle``): a ref already held by another open
    comanda is rejected before the write. Updates both the session handle and
    the ``tab_ref``/``tab_display`` markers the surface reads — written directly
    (no re-pricing of the open comanda).
    """
    channel, _config = _channel_and_config(channel_ref)
    session = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=session_key)
    if session is None:
        raise PosIntentError(
            code="tab_not_found",
            message="Comanda não encontrada.",
            field="session_key",
            focus="cart",
        )

    try:
        ref = normalize_tab_ref(new_tab_ref)
    except ValueError as exc:
        raise PosIntentError(
            code="invalid_tab_ref",
            message=str(exc) or "Referência de comanda inválida.",
            field="new_tab_ref",
            focus="cart",
        ) from exc

    if ref == _session_tab_ref(session):
        return session

    existing = _get_open_pos_tab_session(channel_ref=channel.ref, tab_ref=ref)
    if existing is not None and existing.session_key != session.session_key:
        raise PosIntentError(
            code="tab_in_use",
            message="Já existe uma comanda aberta com essa referência.",
            field="new_tab_ref",
            focus="cart",
        )

    old_ref = _session_tab_ref(session)
    tab_display = _ensure_pos_tab(ref, display=_tab_label_from_input(new_tab_ref, ref))
    session_service.assign_handle(
        session_key=session.session_key,
        channel_ref=channel.ref,
        handle_type="pos_tab",
        handle_ref=ref,
    )
    session.refresh_from_db()
    session.data = {**(session.data or {}), "tab_ref": ref, "tab_display": tab_display}
    session.save(update_fields=["data"])

    session.emit_event("tab_renamed", actor=operator_username, payload={"from_ref": old_ref, "to_ref": ref})

    logger.info(
        "pos_rename_tab session=%s new_ref=%s operator=%s",
        session.session_key, ref, operator_username,
    )
    return session


def move_pos_tab_lines(
    *,
    channel_ref: str,
    from_session_key: str,
    line_ids: list[str],
    to_session_key: str = "",
    to_tab_ref: str = "",
    close_source_when_empty: bool = False,
    actor: str,
    operator_username: str,
) -> PosMoveResult:
    """Move lines between POS comandas (transfer / split / merge), freezing price.

    - transfer: ``to_session_key`` points at an existing open comanda.
    - split: ``to_tab_ref`` names a new comanda; it is created, then the lines
      move into it (suggested child handle is editable on the surface).
    - merge: pass every ``line_id`` plus ``close_source_when_empty`` so the
      emptied source comanda is released.

    Prices carry over verbatim via the kernel ``move_lines`` op.
    """
    channel, _config = _channel_and_config(channel_ref)
    line_ids = [str(line_id) for line_id in (line_ids or []) if str(line_id).strip()]
    if not line_ids:
        raise PosIntentError(
            code="no_line_ids",
            message="Selecione ao menos um item para mover.",
            field="line_ids",
            focus="cart",
        )

    source = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=from_session_key)
    if source is None:
        raise PosIntentError(
            code="tab_not_found",
            message="Comanda de origem não encontrada.",
            field="from_session_key",
            focus="cart",
        )

    target_created = False
    if to_session_key:
        target = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=to_session_key)
        if target is None:
            raise PosIntentError(
                code="tab_not_found",
                message="Comanda de destino não encontrada.",
                field="to_session_key",
                focus="cart",
            )
    elif to_tab_ref:
        ref = normalize_tab_ref(to_tab_ref)
        if not ref:
            raise PosIntentError(
                code="invalid_tab_ref",
                message="Referência de comanda inválida.",
                field="to_tab_ref",
                focus="cart",
            )
        if _get_open_pos_tab_session(channel_ref=channel.ref, tab_ref=ref) is not None:
            raise PosIntentError(
                code="tab_in_use",
                message="Já existe uma comanda aberta com essa referência.",
                field="to_tab_ref",
                focus="cart",
            )
        tab_display = _ensure_pos_tab(ref, display=_tab_label_from_input(to_tab_ref, ref))
        target = session_service.create_session(
            channel.ref,
            handle_type="pos_tab",
            handle_ref=ref,
            data={
                "origin_channel": "pos",
                "fulfillment_type": "pickup",
                "tab_ref": ref,
                "tab_display": tab_display,
                "pos_operator": operator_username,
                "last_touched_at": timezone.now().isoformat(),
            },
        )
        target_created = True
    else:
        raise PosIntentError(
            code="missing_target",
            message="Informe a comanda de destino.",
            field="to_session_key",
            focus="cart",
        )

    if target.session_key == source.session_key:
        raise PosIntentError(
            code="same_tab",
            message="Origem e destino não podem ser a mesma comanda.",
            field="to_session_key",
            focus="cart",
        )

    try:
        session_service.move_session_lines(
            from_session_key=source.session_key,
            to_session_key=target.session_key,
            channel_ref=channel.ref,
            line_ids=line_ids,
        )
    except Exception as exc:  # noqa: BLE001 - surface kernel errors as a recoverable POS error
        logger.warning(
            "pos_move_tab_lines_failed from=%s to=%s: %s",
            source.session_key, target.session_key, exc,
        )
        if target_created:
            # Roll back the freshly-created split target so no empty comanda lingers.
            # Guard the cleanup: a failure abandoning the target must not mask the
            # original move error the operator needs to see.
            try:
                session_service.abandon_session(session_key=target.session_key, channel_ref=channel.ref)
            except Exception:  # noqa: BLE001 - cleanup is best-effort; original error wins
                logger.exception(
                    "pos_move_tab_lines_rollback_failed target=%s", target.session_key
                )
        raise PosIntentError(
            code="move_failed",
            message=str(exc) or "Falha ao mover itens entre comandas.",
            field="line_ids",
            focus="cart",
        ) from exc

    source.refresh_from_db()
    target.refresh_from_db()

    source_closed = False
    if close_source_when_empty and not source.items:
        source_closed = session_service.abandon_session(
            session_key=source.session_key,
            channel_ref=channel.ref,
        )

    logger.info(
        "pos_move_tab_lines from=%s to=%s count=%s split=%s closed=%s operator=%s",
        source.session_key,
        target.session_key,
        len(line_ids),
        target_created,
        source_closed,
        operator_username,
    )
    return PosMoveResult(
        target=target,
        source=None if source_closed else source,
        source_closed=bool(source_closed),
    )


def _session_to_fire_lines(session: Session) -> list[dict]:
    """Normalize an open comanda's items to source-agnostic KDS fire lines."""
    lines = []
    for item in (session.items or []):
        meta = item.get("meta") or {}
        lines.append({
            "line_id": item.get("line_id", ""),
            "sku": item.get("sku", ""),
            "name": item.get("name") or item.get("sku", ""),
            "qty": int(item.get("qty", 1)),
            "notes": meta.get("notes", ""),
            "meta": meta,
        })
    return lines


def fire_pos_tab(
    *,
    channel_ref: str,
    session_key: str,
    line_ids: list[str] | None = None,
    client_request_id: str = "",
    actor: str,
    operator_username: str,
) -> PosFireResult:
    """Send an open comanda's not-yet-fired courses to the kitchen (KDS).

    Progressive (course-by-course): only the unfired delta is dispatched.
    ``line_ids`` (optional) limits the fire to specific lines; omitted means
    "fire the whole tab" (every still-unfired line). Idempotent — the kitchen
    ticket ledger keyed by ``session_key`` is authoritative, so re-sending a
    course is a no-op and a cancelled course may re-fire (reprint).

    Payment is never stored on the comanda: an open tab is unpaid by nature, so
    "fired + unpaid" is derived downstream (``session_key → Order → payman``) as
    a free anti-fraud signal.
    """
    from shopman.shop.services import kds as kds_service

    channel, _config = _channel_and_config(channel_ref)
    session = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=session_key)
    if session is None:
        raise PosIntentError(
            code="tab_not_found",
            message="Comanda não encontrada.",
            field="session_key",
            focus="cart",
        )

    requested = {str(lid).strip() for lid in (line_ids or []) if str(lid).strip()}
    lines = _session_to_fire_lines(session)
    if requested:
        lines = [ln for ln in lines if ln["line_id"] in requested]
    if not lines:
        raise PosIntentError(
            code="no_lines",
            message="Não há itens para enviar à cozinha.",
            field="line_ids",
            focus="cart",
        )

    tickets = kds_service.fire_lines(session_key=session.session_key, lines=lines)

    # Mirror the fired-line ledger onto the comanda for the cart UI. The kitchen
    # tickets stay authoritative; this marker is a cheap read for the projection
    # and is written directly (no re-pricing of the open comanda).
    fired = sorted(kds_service.fired_line_ids(session.session_key))
    session.data = {**(session.data or {}), "fired_lines": fired}
    session.save(update_fields=["data"])

    session.emit_event("fired", actor=operator_username, payload={
        "lines": [{"sku": ln["sku"], "name": ln["name"], "qty": ln["qty"]} for ln in lines],
        "count": len(tickets),
    })

    logger.info(
        "pos_fire_tab tab=%s session=%s fired_now=%d total_fired=%d operator=%s req=%s",
        _session_tab_ref(session), session.session_key, len(tickets), len(fired),
        operator_username, client_request_id or "-",
    )
    return PosFireResult(session=session, fired_count=len(tickets), fired_lines=tuple(fired))


def cancel_fired_pos_tab_lines(
    *,
    channel_ref: str,
    session_key: str,
    line_ids: list[str],
    actor: str,
    operator_username: str,
) -> PosUnfireResult:
    """Cancel the kitchen fire for specific comanda lines (course returned/wrong).

    The targeted lines leave their live KDS tickets (a ticket is cancelled when
    it empties), drop from ``Session.data["fired_lines"]`` and become re-fireable
    — so a reprint is simply cancel + fire again. The kitchen sees the change via
    the ticket's SSE event.
    """
    from shopman.shop.services import kds as kds_service

    channel, _config = _channel_and_config(channel_ref)
    session = _get_open_pos_tab_session_by_key(channel_ref=channel.ref, session_key=session_key)
    if session is None:
        raise PosIntentError(
            code="tab_not_found",
            message="Comanda não encontrada.",
            field="session_key",
            focus="cart",
        )

    targets = [str(lid).strip() for lid in (line_ids or []) if str(lid).strip()]
    if not targets:
        raise PosIntentError(
            code="no_lines",
            message="Selecione itens para cancelar o envio.",
            field="line_ids",
            focus="cart",
        )

    target_set = set(targets)
    unfired_lines = [
        {"sku": i.get("sku"), "name": i.get("name"), "qty": _audit_qty(i)}
        for i in session.items if i.get("line_id") in target_set
    ]
    result = kds_service.unfire_lines(session_key=session.session_key, line_ids=targets)
    fired = sorted(kds_service.fired_line_ids(session.session_key))
    session.data = {**(session.data or {}), "fired_lines": fired}
    session.save(update_fields=["data"])

    session.emit_event("unfired", actor=operator_username, payload={
        "lines": unfired_lines, "line_ids": targets, "cancelled": result["cancelled"],
    })

    logger.info(
        "pos_unfire_tab tab=%s session=%s cancelled=%d trimmed=%d total_fired=%d operator=%s",
        _session_tab_ref(session), session.session_key,
        result["cancelled"], result["trimmed"], len(fired), operator_username,
    )
    return PosUnfireResult(
        session=session,
        cancelled=result["cancelled"],
        trimmed=result["trimmed"],
        fired_lines=tuple(fired),
    )


def cancel_recent_order(
    *,
    order_ref: str,
    actor: str,
    max_age_minutes: int = 5,
    channel_ref: str = "pdv",
) -> None:
    """Cancel the last POS order if it is still inside the operator window.

    Escopo: SÓ vendas do canal POS. Pedido de outro canal (web/iFood) tem
    fluxo próprio no gestor, com permissão ``manage_orders`` e, no iFood,
    ``cancellation_code`` — a janela de 5 min do PDV não é um atalho.
    Venda cujo turno de caixa JÁ FECHOU também não: o ``expected_amount_q``
    do fechamento ficaria mentindo, sem movimento de devolução.
    """
    try:
        order = Order.objects.get(ref=order_ref)
    except Order.DoesNotExist as exc:
        raise ValueError(f"Pedido {order_ref} não encontrado") from exc

    if channel_ref and order.channel_ref != channel_ref:
        raise ValueError(
            f"Pedido {order_ref} não é do PDV — cancele pelo gestor de pedidos."
        )

    age = timezone.now() - order.created_at
    if age > timedelta(minutes=max_age_minutes):
        raise ValueError(
            f"Pedido {order_ref} criado há mais de {max_age_minutes} minutos — cancelamento não permitido"
        )
    if order.status not in (Order.Status.NEW, Order.Status.CONFIRMED):
        raise ValueError(f"Pedido {order_ref} não pode ser cancelado (status: {order.status})")
    if _order_cash_shift_closed(order):
        raise ValueError(
            f"O caixa da venda {order_ref} já foi fechado — registre a devolução pelo gestor."
        )

    cancel(order, reason="pos_operator", actor=actor)
    logger.info("pos_cancel_last order=%s actor=%s", order_ref, actor)


def _order_cash_shift_closed(order) -> bool:
    shift_id = ((order.data or {}).get("pos") or {}).get("cash_shift_id")
    if not shift_id:
        return False
    from shopman.shop.adapters import pos as pos_adapter

    return pos_adapter.cash_shift_is_closed(shift_id)


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
    approval = payload.get("manager_approval") or {}
    approved_by = str(approval.get("username") or "").strip()
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
        meta: dict = {}
        notes = str(item.get("notes", "") or "").strip()
        if notes:
            meta["notes"] = notes
        if item.get("price_overridden"):
            # Freeze the operator's unit price: the pricing modifier honors this
            # flag and skips re-pricing. Stamp who approved (manager PIN gate).
            meta["price_overridden"] = True
            if approved_by:
                meta["price_approved_by"] = approved_by
        line_discount = _normalize_line_discount(item.get("discount"))
        if line_discount:
            if approved_by:
                line_discount["approved_by"] = approved_by
            meta["manual_discount"] = line_discount
        if meta:
            op["meta"] = meta
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

    manual_discount = _payload_manual_discount(payload)
    if manual_discount:
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


def _verify_manager_pin(username: str, pin: str):
    """Resolve a manager by username and verify their override PIN.

    A short, rate-limited PIN challenge replaces account passwords in the sale
    payload. Reuses doorman's generic ``PinCredential`` (HMAC hash + lockout)
    and the same ``backstage.adjust_cashshift`` permission the override gates
    require. Returns the authorizing user, or ``None`` if the challenge fails.
    """
    from django.contrib.auth import get_user_model
    from shopman.doorman.models import PinCredential

    user_model = get_user_model()
    try:
        user = user_model.objects.get(username=username, is_active=True, is_staff=True)
    except user_model.DoesNotExist:
        return None
    if not user.has_perm("backstage.adjust_cashshift"):
        return None
    try:
        credential = user.pin_credential
    except PinCredential.DoesNotExist:
        return None
    return user if credential.verify(pin) else None


def validate_manager_approval(payload: dict, *, operator_username: str) -> None:
    """Require a manager PIN challenge for configured POS discount thresholds.

    A manual discount on a D-1 line always requires manager approval (audited
    exception), independent of the configured monetary threshold.
    """
    threshold_q = _discount_approval_threshold_q()
    discount_q = _payload_discount_q(payload)
    d1_forces_approval = _payload_has_d1_line_discount(payload)
    price_override = _payload_has_price_override(payload)
    over_threshold = threshold_q > 0 and discount_q > threshold_q
    if not d1_forces_approval and not over_threshold and not price_override:
        return

    approval = payload.get("manager_approval") or {}
    username = str(approval.get("username") or "").strip()
    pin = str(approval.get("pin") or "")
    if not username or not pin:
        raise PosIntentError(
            code="manager_approval_required",
            message="Esta venda exige aprovação gerencial.",
            field="manager_approval",
            focus="approval",
            recovery="Peça a um gerente autorizado para aprovar com o PIN antes de finalizar.",
        )

    if _verify_manager_pin(username, pin) is None:
        raise PosIntentError(
            code="manager_approval_invalid",
            message="Aprovação gerencial inválida.",
            field="manager_approval",
            focus="approval",
            recovery="Revise o gerente e o PIN, ou reduza o desconto / ajuste o preço.",
        )
    logger.info(
        "pos_manager_approval operator=%s approved_by=%s discount_q=%s price_override=%s",
        operator_username,
        username,
        discount_q,
        price_override,
    )


def _replace_session_ops(session: Session, payload: dict, operator_username: str) -> list[dict]:
    """Build ops that replace mutable POS payload fields on an existing session.

    Preserva o ``line_id`` por SKU ao reconstruir as linhas: o PDV tem uma linha por
    SKU, então o remove+readd do fechamento pode manter a identidade durável de cada
    linha. Sem isso, os line_ids são regerados e o pedido committado dispara DE NOVO
    pra cozinha (o ledger de fire é por line_id) — comanda preparada em dobro.
    """
    line_id_by_sku: dict[str, str] = {}
    for item in (session.items or []):
        sku = item.get("sku")
        line_id = item.get("line_id")
        if sku and line_id and sku not in line_id_by_sku:
            line_id_by_sku[sku] = line_id

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
    add_ops = build_session_ops(payload, operator_username)
    for op in add_ops:
        if op.get("op") == "add_line":
            preserved = line_id_by_sku.pop(op.get("sku"), None)  # consome (1 linha/SKU)
            if preserved:
                op["line_id"] = preserved
    ops.extend(add_ops)
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
    order_discount_q = int(_payload_manual_discount(payload).get("discount_q", 0) or 0)
    return order_discount_q + _payload_line_discounts_q(payload)


def _normalize_line_discount(raw) -> dict:
    """Normalize an operator per-line discount (percent only) from the intent."""
    if not isinstance(raw, dict):
        return {}
    try:
        value = float(raw.get("value") or 0)
    except (TypeError, ValueError):
        return {}
    if value <= 0:
        return {}
    reason = str(raw.get("reason") or "cortesia").strip()[:120] or "cortesia"
    return {"type": "percent", "value": value, "reason": reason}


def _payload_line_discounts_q(payload: dict) -> int:
    """Sum per-line manual discounts (percent, per unit, clamped) for preview/gate."""
    total = 0
    for item in payload.get("items", []):
        line_discount = _normalize_line_discount(item.get("discount"))
        if not line_discount:
            continue
        try:
            unit_price_q = int(item.get("unit_price_q", 0))
            qty = int(item.get("qty", 1))
        except (TypeError, ValueError):
            continue
        per_unit = min(int(round(unit_price_q * line_discount["value"] / 100)), unit_price_q)
        total += max(0, per_unit) * max(0, qty)
    return total


def _payload_has_d1_line_discount(payload: dict) -> bool:
    """True if any D-1 line carries a manual discount (always needs approval)."""
    return any(
        item.get("is_d1") and _normalize_line_discount(item.get("discount"))
        for item in payload.get("items", [])
    )


def _payload_has_price_override(payload: dict) -> bool:
    """True if any line carries an operator unit-price override (numpad "Preço").

    Flag-driven (the client knows when the operator overrode), not a price
    comparison — robust against D-1/Happy-Hour and listing-vs-base differences.
    Always requires manager approval."""
    return any(item.get("price_overridden") for item in payload.get("items", []))


def _payload_manual_discount(payload: dict) -> dict:
    manual_discount = payload.get("manual_discount") or {}
    if not isinstance(manual_discount, dict):
        return {}

    subtotal_q = _payload_subtotal_q(payload)
    if subtotal_q <= 0:
        return {}

    type_ref = str(manual_discount.get("type") or "percent").strip().lower()
    if type_ref not in {"percent", "fixed"}:
        type_ref = "percent"

    value = _decimal_discount_value(manual_discount.get("value"))
    fallback_q = _int_q(manual_discount.get("discount_q"))
    if value > 0:
        if type_ref == "fixed":
            discount_q = int((value * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            discount_q = int((Decimal(subtotal_q) * value / Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    else:
        discount_q = fallback_q
        value = _decimal_discount_value(manual_discount.get("value") or 0)

    discount_q = min(subtotal_q, max(0, discount_q))
    if discount_q <= 0:
        return {}

    reason = str(manual_discount.get("reason") or "cortesia").strip()[:120] or "cortesia"
    return {
        "type": type_ref,
        "value": float(value) if value > 0 else manual_discount.get("value", 0),
        "discount_q": discount_q,
        "reason": reason,
    }


def _decimal_discount_value(value) -> Decimal:
    if isinstance(value, str):
        raw = value.strip()
        raw = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    else:
        raw = str(value or "0")
    try:
        parsed = Decimal(raw)
    except (InvalidOperation, ValueError):
        return Decimal("0")
    return max(Decimal("0"), parsed)


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
        require_complete=True,
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
    require_complete: bool = False,
) -> list[dict]:
    raw = payload.get("payment_tenders")
    payment_method = _normalize_payment_method(payload.get("payment_method") or "cash")
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
            if collection == "on_delivery" and method != "cash":
                raise PosIntentError(
                    code="invalid_on_delivery_tender_payment",
                    message="Pagamento na entrega só é permitido em dinheiro.",
                    field=f"payment_tenders.{len(tenders)}.collection",
                    focus="payment",
                    recovery="Altere a linha para dinheiro ou receba esse valor no caixa.",
                )
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
        if require_complete and total_q > 0 and paid_q < total_q:
            raise PosIntentError(
                code="payment_tenders_total_mismatch",
                message="Os pagamentos informados não cobrem o total da venda.",
                field="payment_tenders",
                focus="payment",
                recovery="Ajuste as linhas do pagamento até cobrirem o total revisado (o excedente vira troco).",
            )
        return tenders

    if total_q <= 0:
        return []
    if require_complete and payment_method == "mixed":
        raise PosIntentError(
            code="payment_tenders_required",
            message="Informe as linhas do pagamento misto.",
            field="payment_tenders",
            focus="payment",
            recovery="Adicione ao menos uma linha e confira se a soma fecha o total.",
        )
    if payment_method == "mixed":
        return []
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
    requested = _normalize_payment_method(payload.get("payment_method") or "cash")
    if requested == "mixed" and tenders:
        return "mixed"
    methods = {str(tender.get("method") or "").strip() for tender in tenders if tender.get("amount_q")}
    methods.discard("")
    if len(methods) > 1:
        return "mixed"
    if len(methods) == 1:
        return next(iter(methods))
    return requested


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


def _maybe_initiate_pos_gateway_payment(order: Order) -> dict:
    """Create gateway payment display data for POS terminal digital tenders."""
    payment = dict((order.data or {}).get("payment") or {})
    method = str(payment.get("method") or "").strip().lower()
    collection = str(payment.get("collection") or "terminal").strip().lower()
    if collection != "terminal" or method not in {"pix", "card"}:
        return {}

    try:
        payment_service.initiate(order)
    except Exception as exc:
        logger.warning("pos_payment_initiate_failed order=%s method=%s", order.ref, method, exc_info=True)
        return {
            "method": method,
            "amount_q": int(payment.get("amount_q") or order.total_q or 0),
            "amount_display": f"R$ {format_money(int(payment.get('amount_q') or order.total_q or 0))}",
            "status": "error",
            "error": str(exc),
            "message": "Pagamento não foi criado no gateway. Revise a configuração e use recuperação operacional.",
        }
    order = Order.objects.get(ref=order.ref)
    return _pos_payment_response(order)


def _pos_payment_response(order: Order) -> dict:
    payment = dict((order.data or {}).get("payment") or {})
    method = str(payment.get("method") or "").strip().lower()
    if method not in {"pix", "card"}:
        return {}

    response = {
        "method": method,
        "amount_q": int(payment.get("amount_q") or order.total_q or 0),
        "amount_display": f"R$ {format_money(int(payment.get('amount_q') or order.total_q or 0))}",
    }
    for key in (
        "intent_ref",
        "qr_code",
        "copy_paste",
        "expires_at",
        "checkout_url",
        "error",
    ):
        value = payment.get(key)
        if value:
            response[key] = value
    if payment.get("intent_ref"):
        response["status"] = "pending"
        response["message"] = "Pagamento criado. Aguarde confirmação do gateway antes de tratar como recebido."
    elif payment.get("error"):
        response["status"] = "error"
        response["message"] = "Pagamento não foi criado no gateway. Revise a configuração e use recuperação operacional."
    else:
        response["status"] = "unavailable"
        response["message"] = "Pagamento digital não retornou dados exibíveis."
    return response


def _reconcile_tenders_to_total(tenders: list[dict], final_total_q: int) -> None:
    if not tenders:
        return
    if len(tenders) == 1:
        tenders[0]["amount_q"] = final_total_q
        return

    remaining_delta_q = final_total_q - sum(_int_q(tender.get("amount_q")) for tender in tenders)
    if remaining_delta_q == 0:
        return

    # Troco/ajuste sai do DINHEIRO: numa venda mista [cash 50, pix 20] p/ 60,
    # o excedente é o troco da nota de 50 — a maquininha capturou os 20
    # inteiros. Descontar da tender eletrônica erraria o caixa (falta falsa
    # no turno) e os totais do fechamento. Eletrônicas só em último caso.
    def _is_cash(tender: dict) -> bool:
        return str(tender.get("method") or "").lower() == "cash"

    ordered = [t for t in reversed(tenders) if _is_cash(t)] + [
        t for t in reversed(tenders) if not _is_cash(t)
    ]
    for tender in ordered:
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


def _payload_tab_ref(payload: dict) -> str:
    raw = str(payload.get("tab_ref") or "").strip()
    return normalize_tab_ref(raw) if raw else ""


def _payload_open_tab_session(*, channel_ref: str, payload: dict) -> Session | None:
    session_key = _payload_tab_session_key(payload)
    if session_key:
        return _get_open_pos_tab_session_by_key(channel_ref=channel_ref, session_key=session_key)
    tab_ref = _payload_tab_ref(payload)
    if tab_ref:
        return _get_open_pos_tab_session(channel_ref=channel_ref, tab_ref=tab_ref)
    return None


def _payload_has_tab_identity(payload: dict) -> bool:
    return bool(_payload_tab_session_key(payload) or _payload_tab_ref(payload))


def _create_direct_checkout_session(*, channel_ref: str, payload: dict, operator_username: str) -> Session:
    now = timezone.now().isoformat()
    return session_service.create_session(
        channel_ref,
        data={
            "origin_channel": "pos",
            "fulfillment_type": _payload_fulfillment_type(payload),
            "pos_operator": operator_username,
            "last_touched_at": now,
            "pos": {
                "direct_checkout": True,
            },
        },
    )


def _get_open_pos_tab_session_by_key(*, channel_ref: str, session_key: str) -> Session | None:
    return Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).first()


def _get_open_pos_tab_session(*, channel_ref: str, tab_ref: str) -> Session | None:
    return Session.objects.filter(
        Q(handle_type="pos_tab", handle_ref=tab_ref) | Q(data__tab_ref=tab_ref),
        channel_ref=channel_ref,
        state="open",
    ).order_by("-opened_at").first()


def _session_tab_ref(session: Session) -> str:
    data = session.data or {}
    raw = str(data.get("tab_ref") or session.handle_ref or "").strip()
    return normalize_tab_ref(raw)


def _session_tab_display(session: Session) -> str:
    data = session.data or {}
    display = str(data.get("tab_display") or "").strip()
    if display:
        return display
    return display_tab_ref(_session_tab_ref(session))


def _ensure_pos_tab(tab_ref: str, display: str = "") -> str:
    return pos_adapter.ensure_tab(ref=tab_ref, display=display or display_tab_ref(tab_ref))


def _mark_tab_committed(
    *,
    order_ref: str,
    tab_ref: str,
    operator_username: str,
    session_data: dict | None = None,
) -> None:
    now = timezone.now().isoformat()

    order = Order.objects.filter(ref=order_ref).first()
    if order is None:
        return
    order_data = dict(order.data or {})
    order_data["pos_operator"] = operator_username
    order_data["pos_committed_at"] = now
    session_data = session_data or {}
    if tab_ref:
        order_data["tab_ref"] = tab_ref
        order_data["tab_display"] = str(session_data.get("tab_display") or display_tab_ref(tab_ref))
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


def resolve_or_create_customer(
    *, name: str = "", phone: str = "", tax_id: str = "", email: str = "", operator_username: str,
) -> dict:
    """Get-or-create a POS customer JUST-IN-TIME — when the operator defines them
    on the counter, not deferred to order commit. Resolves by phone/CPF/email or
    creates a fresh record, and returns the customer dict (ref/name/phone/tax_id/
    email/group). Idempotent (same identifiers → same customer). Reuses the exact
    commit-time logic so the just-in-time customer is identical to the final one."""
    return _persist_customer_from_payload(
        {
            "customer_name": name,
            "customer_phone": phone,
            "customer_tax_id": tax_id,
            "customer_email": email,
        },
        operator_username=operator_username,
    )


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
