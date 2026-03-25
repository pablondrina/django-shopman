from __future__ import annotations

from decimal import Decimal

from django.http import HttpRequest
from shopman.ordering.ids import generate_session_key
from shopman.ordering.models import Channel, Session
from shopman.ordering.services.modify import ModifyService
from shopman.utils.monetary import format_money

CHANNEL_REF = "web"


class CartService:
    """Manages Ordering sessions linked to Django visitor sessions."""

    @staticmethod
    def _get_channel() -> Channel:
        return Channel.objects.get(ref=CHANNEL_REF)

    @staticmethod
    def _get_session_key(request: HttpRequest) -> str | None:
        return request.session.get("cart_session_key")

    @staticmethod
    def _get_or_create_session(request: HttpRequest) -> tuple[Session, str]:
        """Return (ordering_session, session_key). Creates if needed."""
        session_key = request.session.get("cart_session_key")
        channel = CartService._get_channel()

        if session_key:
            try:
                ordering_session = Session.objects.get(
                    session_key=session_key,
                    channel=channel,
                    state="open",
                )
                return ordering_session, session_key
            except Session.DoesNotExist:
                pass

        # Create new session
        session_key = generate_session_key()
        ordering_session = Session.objects.create(
            session_key=session_key,
            channel=channel,
            pricing_policy=channel.pricing_policy,
            edit_policy=channel.edit_policy,
        )
        request.session["cart_session_key"] = session_key
        return ordering_session, session_key

    @staticmethod
    def add_item(request: HttpRequest, sku: str, qty: int, unit_price_q: int) -> Session:
        """Add item to cart. Merges with existing line if same SKU."""
        session, session_key = CartService._get_or_create_session(request)

        # Merge: if SKU already in cart, increment qty instead of adding new line
        existing = next((item for item in session.items if item.get("sku") == sku), None)
        if existing:
            new_qty = int(Decimal(str(existing["qty"]))) + qty
            return ModifyService.modify_session(
                session_key=session_key,
                channel_ref=CHANNEL_REF,
                ops=[{"op": "set_qty", "line_id": existing["line_id"], "qty": new_qty}],
            )

        return ModifyService.modify_session(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            ops=[{"op": "add_line", "sku": sku, "qty": qty, "unit_price_q": unit_price_q}],
        )

    @staticmethod
    def update_qty(request: HttpRequest, line_id: str, qty: int) -> Session:
        """Update quantity of a cart item."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            raise ValueError("No active cart")
        return ModifyService.modify_session(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            ops=[{"op": "set_qty", "line_id": line_id, "qty": qty}],
        )

    @staticmethod
    def remove_item(request: HttpRequest, line_id: str) -> Session:
        """Remove item from cart."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            raise ValueError("No active cart")
        return ModifyService.modify_session(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            ops=[{"op": "remove_line", "line_id": line_id}],
        )

    @staticmethod
    def get_cart(request: HttpRequest) -> dict:
        """Return cart data: items, subtotal, count (total units)."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            return {"items": [], "subtotal_q": 0, "subtotal_display": "R$ 0,00", "count": 0}

        channel = CartService._get_channel()
        try:
            session = Session.objects.get(
                session_key=session_key,
                channel=channel,
                state="open",
            )
        except Session.DoesNotExist:
            request.session.pop("cart_session_key", None)
            return {"items": [], "subtotal_q": 0, "subtotal_display": "R$ 0,00", "count": 0}

        items = session.items
        subtotal_q = sum(item.get("line_total_q", 0) for item in items)
        count = sum(int(Decimal(str(item.get("qty", 0)))) for item in items)

        # Enrich items with display info
        for item in items:
            item["price_display"] = f"R$ {format_money(item.get('unit_price_q', 0))}"
            item["total_display"] = f"R$ {format_money(item.get('line_total_q', 0))}"

        return {
            "items": items,
            "subtotal_q": subtotal_q,
            "subtotal_display": f"R$ {format_money(subtotal_q)}",
            "count": count,
            "session_key": session_key,
        }

    @staticmethod
    def apply_coupon(request: HttpRequest, code: str) -> dict:
        """Validate and apply a coupon code to the cart session."""
        from shop.models import Coupon

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

        # Store coupon in session data and re-run modifiers
        channel = CartService._get_channel()
        try:
            session = Session.objects.get(session_key=session_key, channel=channel, state="open")
        except Session.DoesNotExist:
            return {"ok": False, "error": "no_cart"}

        data = session.data or {}
        data["coupon_code"] = code
        session.data = data
        session.save(update_fields=["data"])

        # Re-run modify to trigger CouponModifier
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            ops=[],
        )

        return {"ok": True, "code": code, "promotion": promo.name}

    @staticmethod
    def remove_coupon(request: HttpRequest) -> dict:
        """Remove coupon from cart session."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            return {"ok": False, "error": "no_cart"}

        channel = CartService._get_channel()
        try:
            session = Session.objects.get(session_key=session_key, channel=channel, state="open")
        except Session.DoesNotExist:
            return {"ok": False, "error": "no_cart"}

        data = session.data or {}
        data.pop("coupon_code", None)
        session.data = data
        session.save(update_fields=["data"])

        # Re-run modify to clear coupon pricing
        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            ops=[],
        )

        if not session.pricing:
            session.pricing = {}
        session.pricing.pop("coupon", None)

        return {"ok": True}

    @staticmethod
    def clear(request: HttpRequest) -> None:
        """Abandon the current session."""
        session_key = CartService._get_session_key(request)
        if not session_key:
            return

        channel = CartService._get_channel()
        try:
            session = Session.objects.get(
                session_key=session_key,
                channel=channel,
                state="open",
            )
            session.state = "abandoned"
            session.save(update_fields=["state"])
        except Session.DoesNotExist:
            pass

        request.session.pop("cart_session_key", None)
