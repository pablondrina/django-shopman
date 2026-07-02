"""Checkout orchestration facade.

This is the single composed checkout path for external surfaces. It resolves
channel configuration, applies checkout/session operations, and commits through
Orderman via ``shopman.shop.services.sessions``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from types import SimpleNamespace

from shopman.shop.config import ChannelConfig
from shopman.shop.models import Channel
from shopman.shop.services import sessions

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckoutResult:
    order_ref: str
    status: str
    total_q: int
    items_count: int


@dataclass(frozen=True)
class CheckoutDomainError:
    detail: str
    error_code: str
    context: dict
    http_status: int


def process(
    session_key: str,
    channel_ref: str,
    data: dict,
    *,
    idempotency_key: str,
    ctx: dict | None = None,
    expected_total_q: int | None = None,
) -> CheckoutResult:
    """Convert checkout data to session operations and commit."""
    customer = data.get("customer") or {}
    phone = customer.get("phone") if isinstance(customer, dict) else ""
    if phone:
        sessions.assign_phone_handle(
            session_key=session_key,
            channel_ref=channel_ref,
            phone=phone,
        )
    result = process_ops(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=_build_ops_from_data(data),
        idempotency_key=idempotency_key,
        ctx=ctx,
        expected_total_q=expected_total_q,
    )
    _apply_post_commit_side_effects(data, channel_ref, order_ref=result.order_ref)
    return result


def process_ops(
    *,
    session_key: str,
    channel_ref: str,
    ops: list[dict],
    idempotency_key: str,
    ctx: dict | None = None,
    expected_total_q: int | None = None,
) -> CheckoutResult:
    """Apply already-built session operations and commit."""
    ctx = ctx or {}
    channel = Channel.objects.get(ref=channel_ref)
    resolved_config = ChannelConfig.for_channel(channel).to_dict()

    if ops:
        sessions.modify_session(
            session_key=session_key,
            channel_ref=channel_ref,
            ops=ops,
            ctx=ctx,
            channel_config=resolved_config,
        )

    # O total que o cliente VIU é o total cobrado. A repricing final (preço de
    # catálogo, cupom expirado) pode ter mudado o valor — commitar um total
    # diferente do exibido, sem confirmação, é cobrança surpresa.
    if expected_total_q is not None:
        _ensure_total_matches(session_key, channel_ref, int(expected_total_q))

    commit = sessions.commit_session(
        session_key=session_key,
        channel_ref=channel_ref,
        idempotency_key=idempotency_key,
        ctx=ctx,
        channel_config=resolved_config,
    )

    logger.info("checkout.process: order %s committed for channel %s", commit.order_ref, channel_ref)
    return CheckoutResult(
        order_ref=commit.order_ref,
        status=commit.status,
        total_q=commit.total_q,
        items_count=commit.items_count,
    )


def _ensure_total_matches(session_key: str, channel_ref: str, expected_total_q: int) -> None:
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError
    from shopman.orderman.models import Session
    from shopman.utils.monetary import format_money

    session = Session.objects.filter(session_key=session_key, channel_ref=channel_ref).first()
    if session is None:
        return
    current_total_q = sum(int(item.get("line_total_q") or 0) for item in (session.items or []))
    if current_total_q == expected_total_q:
        return
    raise OrderingValidationError(
        code="total_changed",
        message=(
            f"O total do pedido mudou para R$ {format_money(current_total_q)} "
            "(preço ou cupom atualizado). Confira e confirme novamente."
        ),
    )


def map_checkout_error(exc: Exception) -> dict[str, str] | None:
    """Map domain validation exceptions to checkout form errors."""
    from django.core.exceptions import ValidationError as DjangoValidationError
    from shopman.orderman.exceptions import ValidationError as OrderingValidationError

    if isinstance(exc, OrderingValidationError):
        address_codes = {"delivery_zone_not_covered", "delivery_zone_unverified"}
        field = "delivery_address" if exc.code in address_codes else "checkout"
        return {field: exc.message}
    if isinstance(exc, DjangoValidationError):
        msgs = exc.messages if hasattr(exc, "messages") else [str(exc)]
        return {"checkout": msgs[0] if msgs else str(exc)}
    return None


def map_order_error(exc: Exception) -> CheckoutDomainError | None:
    """Map Orderman checkout errors without leaking Orderman imports to surfaces."""
    from shopman.orderman.exceptions import OrderError

    if not isinstance(exc, OrderError):
        return None

    code = getattr(exc, "code", "checkout_error")
    conflict_codes = {"in_progress", "blocking_issues", "stale_checks", "hold_expired"}
    http_status = 409 if code in conflict_codes else 400
    return CheckoutDomainError(
        detail=getattr(exc, "message", str(exc)),
        error_code=code,
        context=getattr(exc, "context", {}),
        http_status=http_status,
    )


def ensure_customer(intent) -> None:
    """Ensure the checkout customer exists in Guestman."""
    import uuid as uuid_lib

    from django.db import IntegrityError
    from shopman.guestman.services import customer as customer_service

    customer_obj = customer_service.get_by_phone(intent.customer_phone)
    if customer_obj:
        if intent.customer_name and not customer_obj.first_name:
            customer_obj.first_name = intent.customer_name
            customer_obj.save(update_fields=["first_name"])
        return

    try:
        customer_service.create(
            ref=f"WEB-{str(uuid_lib.uuid4())[:8].upper()}",
            first_name=intent.customer_name,
            phone=intent.customer_phone,
        )
    except IntegrityError:
        pass


def persist_new_address(intent) -> None:
    """Persist a newly typed delivery address to the checkout customer."""
    if intent.fulfillment_type != "delivery":
        return
    if intent.saved_address_id:
        return
    if not intent.delivery_address:
        return

    from shopman.guestman.services import address as address_service
    from shopman.guestman.services import customer as customer_service

    customer_obj = customer_service.get_by_phone(intent.customer_phone)
    if not customer_obj:
        return

    if address_service.has_address(customer_obj.ref, intent.delivery_address):
        return

    structured = intent.delivery_address_structured or {}

    lat = structured.get("latitude")
    lng = structured.get("longitude")
    coordinates = (float(lat), float(lng)) if lat and lng else None

    components = {
        "street_number": structured.get("street_number", ""),
        "route": structured.get("route", ""),
        "neighborhood": structured.get("neighborhood", ""),
        "city": structured.get("city", ""),
        "state_code": structured.get("state_code", ""),
        "postal_code": structured.get("postal_code", ""),
    }

    is_first = not address_service.has_any_address(customer_obj.ref)

    address_service.add_address(
        customer_ref=customer_obj.ref,
        label="other",
        label_custom="Entrega",
        formatted_address=intent.delivery_address,
        place_id=structured.get("place_id") or None,
        components=components,
        coordinates=coordinates,
        complement=structured.get("complement", ""),
        delivery_instructions=structured.get("delivery_instructions", ""),
        is_default=is_first,
    )


def save_defaults(intent, *, order_ref: str, enabled: bool) -> None:
    """Persist explicit checkout defaults when the customer opts in."""
    if not enabled:
        return

    from shopman.guestman.services import customer as customer_service

    from shopman.shop.services.checkout_defaults import CheckoutDefaultsService

    customer_obj = customer_service.get_by_phone(intent.customer_phone)
    if not customer_obj:
        return

    defaults_data: dict = {
        "fulfillment_type": intent.fulfillment_type,
        "payment_method": intent.payment_method,
    }
    if intent.fulfillment_type == "delivery":
        if intent.saved_address_id:
            defaults_data["delivery_address_id"] = intent.saved_address_id
        if intent.delivery_time_slot:
            defaults_data["delivery_time_slot"] = intent.delivery_time_slot
    if intent.notes:
        defaults_data["order_notes"] = intent.notes

    CheckoutDefaultsService.save_defaults(
        customer_ref=customer_obj.ref,
        channel_ref=intent.channel_ref,
        data=defaults_data,
        source=f"order:{order_ref}",
    )


def _post_commit_intent(data: dict, channel_ref: str) -> SimpleNamespace:
    """Lightweight intent built from checkout data for the post-commit side effects.

    Shop never imports the storefront ``CheckoutIntent`` (dependency rule); the side
    effects only read attributes, so a namespace from ``data`` is enough.
    """
    customer = data.get("customer") if isinstance(data.get("customer"), dict) else {}
    payment = data.get("payment") if isinstance(data.get("payment"), dict) else {}
    return SimpleNamespace(
        customer_phone=customer.get("phone") or "",
        customer_name=customer.get("name") or "",
        fulfillment_type=data.get("fulfillment_type", "pickup"),
        saved_address_id=data.get("saved_address_id"),
        delivery_address=data.get("delivery_address"),
        delivery_address_structured=data.get("delivery_address_structured"),
        payment_method=payment.get("method") or "",
        delivery_time_slot=data.get("delivery_time_slot"),
        notes=data.get("order_notes"),
        channel_ref=channel_ref,
    )


def _apply_post_commit_side_effects(data: dict, channel_ref: str, *, order_ref: str) -> None:
    """Persist customer-facing side effects after a successful commit (best-effort).

    Upsert the customer, save a newly typed delivery address to their account, and
    remember their checkout choices as defaults. Hospitality (omotenashi): saving is
    the default; the surface opts OUT via ``save_as_default=false``. None of these may
    break the checkout — the order is already committed.
    """
    intent = _post_commit_intent(data, channel_ref)
    if not intent.customer_phone:
        return

    try:
        ensure_customer(intent)
    except Exception:
        logger.warning("checkout.ensure_customer_failed order=%s", order_ref, exc_info=True)
    try:
        persist_new_address(intent)
    except Exception:
        logger.warning("checkout.persist_new_address_failed order=%s", order_ref, exc_info=True)
    try:
        save_defaults(intent, order_ref=order_ref, enabled=bool(data.get("save_as_default", True)))
    except Exception:
        logger.warning("checkout.save_defaults_failed order=%s", order_ref, exc_info=True)


def order_has_payment_error(order_ref: str) -> bool:
    from shopman.orderman.models import Order

    order = Order.objects.get(ref=order_ref)
    return bool((order.data or {}).get("payment", {}).get("error"))


def starts_payment_after_store_confirmation(channel_ref: str) -> bool:
    try:
        return ChannelConfig.for_channel(channel_ref).payment.timing == "post_commit"
    except Exception:
        logger.warning("payment_timing_lookup_failed channel=%s", channel_ref, exc_info=True)
        return False


def get_open_cart_session(*, session_key: str, channel_ref: str):
    from shopman.orderman.models import Session

    return Session.objects.get(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    )


def simulate_ifood_order(cart_session):
    from shopman.shop.services import ifood_ingest
    from shopman.shop.services.ifood_simulation import session_to_ifood_payload

    payload = session_to_ifood_payload(cart_session)
    return ifood_ingest.ingest(payload)


def close_cart_session(cart_session) -> None:
    cart_session.state = "closed"
    cart_session.save(update_fields=["state", "updated_at"])


def _build_ops_from_data(data: dict) -> list[dict]:
    """Convert checkout data dict into Orderman session operations."""
    ops = []
    data_fields = [
        "customer",
        "fulfillment_type",
        "delivery_address",
        "saved_address_id",
        "delivery_address_structured",
        "delivery_date",
        "delivery_time_slot",
        "order_notes",
        "payment",
        "loyalty",
        "manual_discount",
        "stock_check_unavailable",
        "is_gift",
        "recipient",
        "gift_message",
        "gift_hide_values",
    ]
    for field in data_fields:
        if field in data:
            ops.append({"op": "set_data", "path": field, "value": data[field]})
    return ops
