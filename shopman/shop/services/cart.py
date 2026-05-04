"""Cart command facade.

Storefront owns HTTP/session concerns and cart presentation. This module owns
the writes against Orderman sessions and Stockman holds for cart mutations.
"""

from __future__ import annotations

from decimal import Decimal

from shopman.orderman.models import Session

from shopman.shop.services import availability
from shopman.shop.services import sessions as session_service


class CartUnavailableError(Exception):
    """Raised when a cart mutation cannot reserve the requested stock."""

    def __init__(
        self,
        sku: str,
        requested_qty: int,
        available_qty: int,
        is_paused: bool,
        substitutes: list[dict],
        error_code: str,
        is_planned: bool = False,
        planned_target_date=None,
    ):
        super().__init__(f"unavailable: sku={sku} qty={requested_qty} avail={available_qty}")
        self.sku = sku
        self.requested_qty = requested_qty
        self.available_qty = available_qty
        self.is_paused = is_paused
        self.substitutes = substitutes
        self.error_code = error_code
        self.is_planned = is_planned
        self.planned_target_date = planned_target_date


def get_open_session(*, session_key: str, channel_ref: str) -> Session | None:
    """Return an open cart session, if it still exists."""
    return Session.objects.filter(
        session_key=session_key,
        channel_ref=channel_ref,
        state="open",
    ).first()


def get_or_create_session(
    *,
    session_key: str | None,
    channel_ref: str,
    origin_channel: str,
) -> tuple[Session, str]:
    """Return an open session key for cart commands."""
    if session_key:
        session = get_open_session(session_key=session_key, channel_ref=channel_ref)
        if session is not None:
            return session, session.session_key

    session = session_service.create_session(
        channel_ref,
        data={"origin_channel": origin_channel},
    )
    return session, session.session_key


def add_item(
    *,
    session_key: str | None,
    channel_ref: str,
    origin_channel: str,
    sku: str,
    qty: int,
    unit_price_q: int,
    name: str = "",
    is_d1: bool = False,
) -> tuple[Session, str]:
    """Reserve stock and add or merge a cart line."""
    session, resolved_key = get_or_create_session(
        session_key=session_key,
        channel_ref=channel_ref,
        origin_channel=origin_channel,
    )

    existing = next((item for item in session.items if item.get("sku") == sku), None)
    _reserve_or_raise(
        sku=sku,
        qty=qty,
        session_key=resolved_key,
        channel_ref=channel_ref,
    )
    availability.bump_session_hold_expiry(resolved_key)

    if existing:
        new_qty = int(Decimal(str(existing["qty"]))) + qty
        return (
            session_service.modify_session(
                session_key=resolved_key,
                channel_ref=channel_ref,
                ops=[{"op": "set_qty", "line_id": existing["line_id"], "qty": new_qty}],
            ),
            resolved_key,
        )

    op: dict = {"op": "add_line", "sku": sku, "qty": qty, "unit_price_q": unit_price_q}
    if name:
        op["name"] = name
    if is_d1:
        op["is_d1"] = True
    return (
        session_service.modify_session(
            session_key=resolved_key,
            channel_ref=channel_ref,
            ops=[op],
        ),
        resolved_key,
    )


def update_qty(*, session_key: str, channel_ref: str, line_id: str, qty: int) -> Session:
    """Reconcile holds and update a cart line quantity."""
    line = get_line(session_key=session_key, channel_ref=channel_ref, line_id=line_id)
    if line is not None:
        result = availability.reconcile(
            sku=line["sku"],
            new_qty=Decimal(str(qty)),
            session_key=session_key,
            channel_ref=channel_ref,
        )
        if not result["ok"]:
            raise CartUnavailableError(
                sku=line["sku"],
                requested_qty=qty,
                available_qty=int(result["available_qty"]),
                is_paused=result["is_paused"],
                substitutes=result["substitutes"],
                error_code=result["error_code"],
                is_planned=result.get("is_planned", False),
            )

    availability.bump_session_hold_expiry(session_key)
    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[{"op": "set_qty", "line_id": line_id, "qty": qty}],
    )


def remove_item(*, session_key: str, channel_ref: str, line_id: str) -> Session:
    """Reconcile holds and remove a cart line."""
    line = get_line(session_key=session_key, channel_ref=channel_ref, line_id=line_id)
    if line is not None:
        availability.reconcile(
            sku=line["sku"],
            new_qty=Decimal("0"),
            session_key=session_key,
            channel_ref=channel_ref,
        )

    availability.bump_session_hold_expiry(session_key)
    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[{"op": "remove_line", "line_id": line_id}],
    )


def get_line(*, session_key: str, channel_ref: str, line_id: str) -> dict | None:
    """Return the session line dict matching ``line_id``."""
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None
    for item in session.items:
        if item.get("line_id") == line_id:
            return item
    return None


def apply_coupon_code(*, session_key: str, channel_ref: str, code: str) -> Session | None:
    """Attach a validated coupon code and re-run session modifiers."""
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None

    data = session.data or {}
    data["coupon_code"] = code
    session.data = data
    session.save(update_fields=["data"])

    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )


def remove_coupon_code(*, session_key: str, channel_ref: str) -> Session | None:
    """Remove coupon code and re-run session modifiers."""
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None

    data = session.data or {}
    data.pop("coupon_code", None)
    session.data = data
    session.save(update_fields=["data"])

    session = session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )
    if session.pricing and "coupon" in session.pricing:
        pricing = session.pricing
        pricing.pop("coupon", None)
        session.pricing = pricing
        session.save(update_fields=["pricing"])
    return session


def clear_session(*, session_key: str, channel_ref: str) -> None:
    """Abandon the cart session."""
    session_service.abandon_session(session_key=session_key, channel_ref=channel_ref)


def _reserve_or_raise(*, sku: str, qty: int, session_key: str, channel_ref: str) -> None:
    result = availability.reserve(
        sku,
        Decimal(str(qty)),
        session_key=session_key,
        channel_ref=channel_ref,
    )
    if result["ok"]:
        return
    raise CartUnavailableError(
        sku=sku,
        requested_qty=qty,
        available_qty=int(result["available_qty"]),
        is_paused=result["is_paused"],
        substitutes=result["substitutes"],
        error_code=result["error_code"],
        is_planned=result.get("is_planned", False),
    )
