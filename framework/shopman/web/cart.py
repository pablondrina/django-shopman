from __future__ import annotations

from collections import defaultdict
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
        origin_channel = request.session.get("origin_channel", "web")
        ordering_session = Session.objects.create(
            session_key=session_key,
            channel=channel,
            pricing_policy=channel.pricing_policy,
            edit_policy=channel.edit_policy,
            data={"origin_channel": origin_channel},
        )
        request.session["cart_session_key"] = session_key
        return ordering_session, session_key

    @staticmethod
    def add_item(
        request: HttpRequest,
        sku: str,
        qty: int,
        unit_price_q: int,
        *,
        is_d1: bool = False,
    ) -> Session:
        """Add item to cart. Merges with existing line if same SKU.

        ``is_d1`` deve refletir a mesma regra da vitrine (estoque só D-1): assim o
        D1DiscountModifier aplica e o DiscountModifier não empilha promoção automática.
        """
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

        op: dict = {"op": "add_line", "sku": sku, "qty": qty, "unit_price_q": unit_price_q}
        if is_d1:
            op["is_d1"] = True
        return ModifyService.modify_session(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            ops=[op],
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
            return {
                "items": [],
                "subtotal_q": 0,
                "subtotal_display": "R$ 0,00",
                "count": 0,
                "discount_lines": [],
            }

        channel = CartService._get_channel()
        try:
            session = Session.objects.get(
                session_key=session_key,
                channel=channel,
                state="open",
            )
        except Session.DoesNotExist:
            request.session.pop("cart_session_key", None)
            return {
                "items": [],
                "subtotal_q": 0,
                "subtotal_display": "R$ 0,00",
                "count": 0,
                "discount_lines": [],
            }

        items = session.items
        subtotal_q = sum(item.get("line_total_q", 0) for item in items)
        count = sum(int(Decimal(str(item.get("qty", 0)))) for item in items)

        # Enrich items with product name and display info
        from shopman.offering.models import Product

        skus = [item.get("sku", "") for item in items]
        products_by_sku = {
            p.sku: p
            for p in Product.objects.filter(sku__in=skus).only("sku", "name")
        }
        for item in items:
            product = products_by_sku.get(item.get("sku", ""))
            if product and not item.get("name"):
                item["name"] = product.name
            item["price_display"] = f"R$ {format_money(item.get('unit_price_q', 0))}"
            item["total_display"] = f"R$ {format_money(item.get('line_total_q', 0))}"

        # Read discount info from session.pricing (persisted by DiscountModifier)
        pricing = session.pricing or {}
        discount_data = pricing.get("discount", {})
        total_discount_q = discount_data.get("total_discount_q", 0)
        discount_items = {d["sku"]: d for d in discount_data.get("items", [])}

        # Enrich items with discount transparency
        for item in items:
            sku = item.get("sku", "")
            disc = discount_items.get(sku)
            if disc:
                item["original_price_display"] = f"R$ {format_money(disc['original_price_q'])}"
                rn = disc.get("name", "") or ""
                if disc.get("type") == "coupon" and rn:
                    item["discount_label"] = f"Cupom {rn}"
                else:
                    item["discount_label"] = rn

        # Coupon info
        coupon_info = None
        coupon_data = pricing.get("coupon")
        data = session.data or {}
        coupon_code = data.get("coupon_code")

        if coupon_code and coupon_data:
            coupon_discount_q = coupon_data.get("discount_q", 0)
            coupon_info = {
                "code": coupon_code,
                "discount_q": coupon_discount_q,
                "discount_display": f"R$ {format_money(coupon_discount_q)}",
            }

        # Compute original subtotal (before any discounts)
        original_subtotal_q = subtotal_q + total_discount_q

        # Uma linha por origem (promoção ou cupom) para transparência no carrinho
        discount_lines: list[dict] = []
        raw_items = discount_data.get("items") or []
        if raw_items:
            agg: dict[str, int] = defaultdict(int)
            for d in raw_items:
                amt = int(d.get("discount_q", 0)) * int(d.get("qty", 0))
                if amt <= 0:
                    continue
                raw_name = (d.get("name") or "").strip() or "Promoção"
                if d.get("type") == "coupon":
                    label = f"Cupom {raw_name}"
                else:
                    label = raw_name
                agg[label] += amt
            discount_lines = [
                {
                    "label": lab,
                    "amount_q": q,
                    "amount_display": f"R$ {format_money(q)}",
                }
                for lab, q in sorted(agg.items(), key=lambda x: -x[1])
            ]

        # Delivery fee (set by DeliveryFeeModifier when fulfillment_type == "delivery")
        delivery_fee_q = data.get("delivery_fee_q")
        delivery_fee_display = None
        if delivery_fee_q is not None:
            delivery_fee_display = "Grátis" if delivery_fee_q == 0 else f"R$ {format_money(delivery_fee_q)}"

        # Grand total (subtotal + delivery fee)
        grand_total_q = subtotal_q + (delivery_fee_q or 0)

        return {
            "items": items,
            "subtotal_q": subtotal_q,
            "subtotal_display": f"R$ {format_money(subtotal_q)}",
            "count": count,
            "session_key": session_key,
            "coupon": coupon_info,
            "has_discount": total_discount_q > 0,
            "total_discount_q": total_discount_q,
            "total_discount_display": f"R$ {format_money(total_discount_q)}",
            "original_subtotal_q": original_subtotal_q,
            "original_subtotal_display": f"R$ {format_money(original_subtotal_q)}",
            "discount_lines": discount_lines,
            "delivery_fee_q": delivery_fee_q,
            "delivery_fee_display": delivery_fee_display,
            "grand_total_q": grand_total_q,
            "grand_total_display": f"R$ {format_money(grand_total_q)}",
        }

    @staticmethod
    def apply_coupon(request: HttpRequest, code: str) -> dict:
        """Validate and apply a coupon code to the cart session."""
        from shopman.models import Coupon

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

        # Re-run modify to trigger DiscountModifier (coupon)
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
