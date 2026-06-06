from __future__ import annotations

import logging
from decimal import Decimal

from django.http import HttpRequest
from shopman.orderman.models import Session
from shopman.utils.monetary import format_money

from shopman.shop.services import cart as cart_mutations
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF as CHANNEL_REF

logger = logging.getLogger(__name__)


class CartService:
    """Adapter between the Django visitor session and the Orderman cart session.

    Holds the session-key↔Orderman wiring (create, add, update, remove, coupon,
    clear) plus cheap summaries. Cart *data resolution* — availability,
    planned holds, discount transparency, totals — lives in the orchestrator
    read-side ``shop.projections.cart``; ``get_cart`` is the legacy-dict view
    over that projection, kept for the REST serializer / checkout / catalog
    until they consume the projection directly (WP6/D).
    """

    @staticmethod
    def _empty_cart(*, include_items: bool = True) -> dict:
        return {
            "items": [] if include_items else [],
            "subtotal_q": 0,
            "subtotal_display": "R$ 0,00",
            "count": 0,
            "discount_lines": [],
        }

    @staticmethod
    def summary_from_session(session: Session, *, include_items: bool = False) -> dict:
        """Return the lightweight cart summary from an already-loaded session."""
        items = [dict(item) for item in (session.items or [])]
        subtotal_q = sum(item.get("line_total_q", 0) for item in items)
        count = sum(int(Decimal(str(item.get("qty", 0)))) for item in items)
        return {
            "items": items if include_items else [],
            "subtotal_q": subtotal_q,
            "subtotal_display": f"R$ {format_money(subtotal_q)}",
            "count": count,
            "discount_lines": [],
        }

    @staticmethod
    def _get_session_key(request: HttpRequest) -> str | None:
        return request.session.get("cart_session_key")

    @staticmethod
    def _get_or_create_session(request: HttpRequest) -> tuple[Session, str]:
        """Return (cart_session, session_key). Creates if needed."""
        cart_session, session_key = cart_mutations.get_or_create_session(
            session_key=request.session.get("cart_session_key"),
            channel_ref=CHANNEL_REF,
            origin_channel=request.session.get("origin_channel", "web"),
        )
        request.session["cart_session_key"] = session_key
        return cart_session, session_key

    @staticmethod
    def add_item(
        request: HttpRequest,
        sku: str,
        qty: int,
        unit_price_q: int,
        *,
        name: str = "",
        is_d1: bool = False,
    ) -> Session:
        """Add item to cart. Merges with existing line if same SKU.

        ``is_d1`` deve refletir a mesma regra da vitrine (estoque só D-1): assim o
        D1DiscountModifier aplica e o DiscountModifier não empilha promoção automática.

        Delegates reservation and session mutation to the shop cart mutation
        facade. On shortage, raises CartUnavailableError with substitutes
        populated so the caller can render a "no stock" UI.

        For merges (existing line), checks availability for the *additional* qty only
        and adopts an additional hold tagged with the same session_key.
        """
        session, session_key = cart_mutations.add_item(
            session_key=CartService._get_session_key(request),
            channel_ref=CHANNEL_REF,
            origin_channel=request.session.get("origin_channel", "web"),
            sku=sku,
            qty=qty,
            unit_price_q=unit_price_q,
            name=name,
            is_d1=is_d1,
        )
        request.session["cart_session_key"] = session_key
        return session

    @staticmethod
    def update_qty(
        request: HttpRequest,
        line_id: str,
        qty: int,
        *,
        sku: str | None = None,
    ) -> Session:
        """Update quantity of a cart item.

        Reconciles holds to the new absolute quantity through the shop cart
        mutation facade. On shortage, raises `CartUnavailableError` and does
        not mutate the cart.
        """
        session_key = CartService._get_session_key(request)
        if not session_key:
            raise ValueError("No active cart")

        return cart_mutations.update_qty(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            line_id=line_id,
            qty=qty,
            sku=sku,
        )

    @staticmethod
    def remove_item(
        request: HttpRequest,
        line_id: str,
        *,
        sku: str | None = None,
    ) -> Session:
        """Remove item from cart.

        Reconciles holds to qty=0 through the shop cart mutation facade, so the
        removed line doesn't bleed reservations until the next commit.
        """
        session_key = CartService._get_session_key(request)
        if not session_key:
            raise ValueError("No active cart")

        return cart_mutations.remove_item(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            line_id=line_id,
            sku=sku,
        )

    @staticmethod
    def _get_line(session_key: str, line_id: str) -> dict | None:
        """Return the session line dict matching `line_id`, or None."""
        session = cart_mutations.get_open_session(session_key=session_key, channel_ref=CHANNEL_REF)
        if session is None:
            return None
        for item in session.items:
            if item.get("line_id") == line_id:
                return item
        return None

    @staticmethod
    def has_items(request: HttpRequest) -> bool:
        """Return whether the visitor has an open cart with positive-qty lines."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            return False

        session = cart_mutations.get_open_session(session_key=session_key, channel_ref=CHANNEL_REF)
        if session is None:
            request.session.pop("cart_session_key", None)
            return False

        for item in session.items:
            try:
                if Decimal(str(item.get("qty", 0))) > 0:
                    return True
            except Exception:
                logger.debug("cart.has_items degraded; using fallback", exc_info=True)
                continue
        return False

    @staticmethod
    def get_cart_summary(request: HttpRequest, *, include_items: bool = False) -> dict:
        """Return a cheap cart summary without stock/catalog enrichment.

        Used by global context and badge endpoints. Availability, planned holds,
        images, discounts transparency and upsells belong to the cart projection
        and should not be paid by every page render.
        """
        session_key = CartService._get_session_key(request)
        if not session_key:
            return CartService._empty_cart(include_items=include_items)

        session = cart_mutations.get_open_session(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
        )
        if session is None:
            request.session.pop("cart_session_key", None)
            return CartService._empty_cart(include_items=include_items)

        return CartService.summary_from_session(session, include_items=include_items)

    @staticmethod
    def get_cart(request: HttpRequest) -> dict:
        """Return the legacy cart dict, built from the cart data projection.

        Data resolution (availability, planned holds, discounts, totals) lives
        in ``shop.projections.cart.build_cart`` — the single source. The REST
        serializer, catalog and discount tests now consume the projection
        directly; this adapter survives only for the **checkout** path
        (``views/intents.checkout``), whose ``checkout_context`` helpers still
        take the dict. It is retired when that drains in WP6/D4.
        """
        from shopman.shop.projections.cart import build_cart

        session_key = CartService._get_session_key(request)
        data = build_cart(session_key, CHANNEL_REF)
        if data.is_empty:
            if session_key and not _session_exists(session_key):
                request.session.pop("cart_session_key", None)
            return CartService._empty_cart()
        return _cart_dict(data)

    @staticmethod
    def apply_coupon(request: HttpRequest, code: str) -> dict:
        """Validate and apply a coupon code to the cart session."""
        from shopman.storefront.models import Coupon

        session_key = CartService._get_session_key(request)
        if not session_key:
            return {"ok": False, "error": "no_cart"}

        code = code.strip().upper()

        try:
            coupon = Coupon.objects.select_related("promotion").get(code=code, is_active=True)
        except Coupon.DoesNotExist:
            return {"ok": False, "error": "invalid_coupon"}

        if not coupon.is_available:
            return {"ok": False, "error": "coupon_exhausted"}

        from django.utils import timezone as tz

        promo = coupon.promotion
        now = tz.now()
        if not promo.is_active or now < promo.valid_from or now > promo.valid_until:
            return {"ok": False, "error": "coupon_expired"}

        session = cart_mutations.apply_coupon_code(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            code=code,
        )
        if session is None:
            return {"ok": False, "error": "no_cart"}

        return {"ok": True, "code": code, "promotion": promo.name}

    @staticmethod
    def remove_coupon(request: HttpRequest) -> dict:
        """Remove coupon from cart session."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            return {"ok": False, "error": "no_cart"}

        session = cart_mutations.remove_coupon_code(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
        )
        if session is None:
            return {"ok": False, "error": "no_cart"}

        return {"ok": True}

    @staticmethod
    def clear(request: HttpRequest) -> None:
        """Abandon the current session."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            return

        cart_mutations.clear_session(session_key=session_key, channel_ref=CHANNEL_REF)
        request.session.pop("cart_session_key", None)


def _session_exists(session_key: str) -> bool:
    return Session.objects.filter(
        session_key=session_key, channel_ref=CHANNEL_REF, state="open",
    ).exists()


def _money(value_q: int | None) -> str:
    return f"R$ {format_money(int(value_q or 0))}"


def _cart_dict(data) -> dict:
    """Format the cart data projection into the legacy dict shape.

    ``data`` is a ``shop.projections.cart.CartProjection``. This is the only
    place the dict view is assembled; it mirrors the fields the REST serializer,
    checkout and discount-transparency callers read.
    """
    items = []
    for line in data.lines:
        item = {
            "line_id": line.line_id,
            "sku": line.sku,
            "name": line.name,
            "qty": line.qty,
            "unit_price_q": line.unit_price_q,
            "line_total_q": line.line_total_q,
            "price_display": _money(line.unit_price_q),
            "total_display": _money(line.line_total_q),
            "is_unavailable": not line.is_available,
            "available_qty": line.available_qty,
            "is_awaiting_confirmation": line.is_awaiting_confirmation,
            "is_ready_for_confirmation": line.is_ready_for_confirmation,
            "confirmation_deadline_iso": line.confirmation_deadline_iso,
            "confirmation_deadline_display": _deadline_display(line.confirmation_deadline_iso),
        }
        if line.original_price_q is not None:
            item["original_price_display"] = _money(line.original_price_q)
        if line.discount_name:
            item["discount_label"] = (
                f"Cupom {line.discount_name}" if line.discount_is_coupon else line.discount_name
            )
        items.append(item)

    coupon = None
    if data.coupon is not None:
        coupon = {
            "code": data.coupon.code,
            "discount_q": data.coupon.discount_q,
            "discount_display": _money(data.coupon.discount_q),
        }

    delivery_fee_display = None
    if data.delivery_fee_q is not None:
        delivery_fee_display = "Grátis" if data.delivery_is_free else _money(data.delivery_fee_q)

    return {
        "items": items,
        "subtotal_q": data.subtotal_q,
        "subtotal_display": _money(data.subtotal_q),
        "count": data.count,
        "session_key": data.session_key,
        "coupon": coupon,
        "has_discount": data.discount_total_q > 0,
        "total_discount_q": data.discount_total_q,
        "total_discount_display": _money(data.discount_total_q),
        "original_subtotal_q": data.original_subtotal_q,
        "original_subtotal_display": _money(data.original_subtotal_q),
        "discount_lines": [
            {
                "label": f"Cupom {dl.name}" if dl.is_coupon else dl.name,
                "amount_q": dl.amount_q,
                "amount_display": _money(dl.amount_q),
            }
            for dl in data.discount_lines
        ],
        "delivery_fee_q": data.delivery_fee_q,
        "delivery_fee_display": delivery_fee_display,
        "grand_total_q": data.grand_total_q,
        "grand_total_display": _money(data.grand_total_q),
    }


def _deadline_display(deadline_iso: str | None) -> str | None:
    if not deadline_iso:
        return None
    try:
        from datetime import datetime

        from django.utils import timezone as _tz

        return _tz.localtime(datetime.fromisoformat(deadline_iso)).strftime("%H:%M")
    except Exception:
        logger.debug("cart._deadline_display degraded", exc_info=True)
        return None
