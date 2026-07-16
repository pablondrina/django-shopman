"""Cart mutation facade.

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


def reprice(*, session_key: str, channel_ref: str) -> Session | None:
    """Re-run session modifiers without mutating lines.

    Used after a non-line change to ``session.data`` (e.g. linking the customer)
    so the pricing reflects it — the discount modifier reads customer group/segment
    from the session. Returns ``None`` if the session is gone.
    """
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None
    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )


def get_or_create_session(
    *,
    session_key: str | None,
    channel_ref: str,
    origin_channel: str,
) -> tuple[Session, str]:
    """Return an open session key for cart mutations."""
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


def update_qty(
    *,
    session_key: str,
    channel_ref: str,
    line_id: str,
    qty: int,
    sku: str | None = None,
) -> Session:
    """Reconcile holds and update a cart line quantity."""
    line_sku = sku
    if line_sku is None:
        line = get_line(session_key=session_key, channel_ref=channel_ref, line_id=line_id)
        line_sku = line["sku"] if line is not None else None
    if line_sku is not None:
        result = availability.reconcile(
            sku=line_sku,
            new_qty=Decimal(str(qty)),
            session_key=session_key,
            channel_ref=channel_ref,
        )
        if not result["ok"]:
            raise CartUnavailableError(
                sku=line_sku,
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


def remove_item(
    *,
    session_key: str,
    channel_ref: str,
    line_id: str,
    sku: str | None = None,
) -> Session:
    """Reconcile holds and remove a cart line."""
    line_sku = sku
    if line_sku is None:
        line = get_line(session_key=session_key, channel_ref=channel_ref, line_id=line_id)
        line_sku = line["sku"] if line is not None else None
    if line_sku is not None:
        availability.reconcile(
            sku=line_sku,
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


def apply_coupon_code(
    *,
    session_key: str,
    channel_ref: str,
    code: str,
    customer: dict | None = None,
) -> Session | None:
    """Attach a validated coupon code and re-run session modifiers.

    When ``customer`` (``{"ref", "group"}``) is given, its identity is merged into
    ``session.data["customer"]`` so a coupon gated by customer group/segment
    computes its discount — the discount modifier resolves the customer's group
    and RFM segment from the session, and does so on every later reprice too.
    Open (non-segmented) coupons pass ``None``.
    """
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None

    data = session.data or {}
    data["coupon_code"] = code
    if customer:
        merged = dict(data.get("customer") or {})
        if customer.get("ref"):
            merged["ref"] = customer["ref"]
        if customer.get("group"):
            merged["group"] = customer["group"]
        if merged:
            data["customer"] = merged
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


def set_delivery_draft(
    *,
    session_key: str,
    channel_ref: str,
    fulfillment_type: str,
    delivery_address_structured: dict | None = None,
) -> Session | None:
    """Persist the chosen fulfillment + delivery address to the session and
    re-run modifiers so the cart reflects the delivery fee (and zone coverage)
    *before* the final commit.

    Read-side preview only — no order is created. The ``DeliveryZoneRule``
    remains the authoritative gate at commit. Clearing ``delivery_fee_q`` and
    ``delivery_zone_error`` forces ``DeliveryFeeModifier`` to recompute against
    the (possibly new) address; on pickup the delivery keys are dropped so the
    fee disappears from the total.
    """
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None

    data = dict(session.data or {})
    data["fulfillment_type"] = fulfillment_type
    data.pop("delivery_fee_q", None)
    data.pop("delivery_zone_error", None)
    if fulfillment_type == "delivery":
        if delivery_address_structured:
            data["delivery_address_structured"] = delivery_address_structured
    else:
        data.pop("delivery_address_structured", None)
        data.pop("delivery_address", None)
    session.data = data
    session.save(update_fields=["data"])

    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )


def set_loyalty_redeem(
    *,
    session_key: str,
    channel_ref: str,
    redeem_q: int,
) -> Session | None:
    """Apply (``redeem_q > 0``) or clear loyalty redemption on the session and
    re-run modifiers.

    The session is the single source of truth for loyalty redemption: both the
    cart and the checkout read ``session.data["loyalty"]`` (via the
    ``loyalty_redeem`` pricing key). Toggling here keeps them in sync instead of
    a UI-only flag that diverges from the discount actually applied.
    """
    session = get_open_session(session_key=session_key, channel_ref=channel_ref)
    if session is None:
        return None

    data = dict(session.data or {})
    if redeem_q > 0:
        data["loyalty"] = {"redeem_points_q": int(redeem_q)}
    else:
        data.pop("loyalty", None)
    session.data = data
    session.save(update_fields=["data"])

    return session_service.modify_session(
        session_key=session_key,
        channel_ref=channel_ref,
        ops=[],
    )


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
