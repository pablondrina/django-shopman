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
    def _customer_link(request: HttpRequest) -> dict | None:
        """Return ``{"ref", "group"}`` for the authenticated viewer, or ``None``.

        Used to persist the customer's identity onto the cart session so a
        promotion/coupon gated by customer group/segment discounts on every
        reprice — the discount modifier resolves the group/segment from the
        session, not from the request.
        """
        from shopman.storefront.identity import get_authenticated_customer

        try:
            customer = get_authenticated_customer(request)
        except Exception:
            # Best-effort pricing context — a resolution failure must never break
            # the cart mutation itself. Degrade to "not linked".
            logger.debug("cart customer link resolution failed", exc_info=True)
            return None
        if customer is None:
            return None
        return {
            "ref": getattr(customer, "ref", "") or "",
            "group": customer.group.ref if getattr(customer, "group_id", None) else "",
        }

    @staticmethod
    def _link_customer(request: HttpRequest, session_key: str) -> bool:
        """Idempotently persist the authenticated customer (ref + group) onto the
        cart session. Returns ``True`` when the session was actually updated.

        No-op for an anonymous viewer or when the session already carries the same
        identity, so it's cheap to call on every cart write.
        """
        payload = CartService._customer_link(request)
        if not payload:
            return False
        session = cart_mutations.get_open_session(
            session_key=session_key, channel_ref=CHANNEL_REF
        )
        if session is None:
            return False
        existing = (session.data or {}).get("customer") or {}
        merged = dict(existing)
        if payload["ref"]:
            merged["ref"] = payload["ref"]
        if payload["group"]:
            merged["group"] = payload["group"]
        if merged == existing:
            return False
        data = dict(session.data or {})
        data["customer"] = merged
        session.data = data
        session.save(update_fields=["data"])
        return True

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
        AvailabilityDiscountModifier aplica e o DiscountModifier não empilha promoção automática.

        Delegates reservation and session mutation to the shop cart mutation
        facade. On shortage, raises CartUnavailableError with substitutes
        populated so the caller can render a "no stock" UI.

        For merges (existing line), checks availability for the *additional* qty only
        and adopts an additional hold tagged with the same session_key.
        """
        # Link the customer to an EXISTING cart before the add reprices, so a
        # segment/group-gated promo already discounts this line. For a brand-new
        # cart (no key yet) the session doesn't exist to write to; we link right
        # after and reprice once below.
        existing_key = CartService._get_session_key(request)
        if existing_key:
            CartService._link_customer(request, existing_key)

        session, session_key = cart_mutations.add_item(
            session_key=existing_key,
            channel_ref=CHANNEL_REF,
            origin_channel=request.session.get("origin_channel", "web"),
            sku=sku,
            qty=qty,
            unit_price_q=unit_price_q,
            name=name,
            is_d1=is_d1,
        )
        request.session["cart_session_key"] = session_key
        if not existing_key and CartService._link_customer(request, session_key):
            session = (
                cart_mutations.reprice(session_key=session_key, channel_ref=CHANNEL_REF)
                or session
            )
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

        CartService._link_customer(request, session_key)
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

        CartService._link_customer(request, session_key)
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
    def _customer_eligible_for_promo(customer, promo) -> bool:
        """True se ``customer`` satisfaz o alvo POR CLIENTE da promoção.

        Só valida restrições que dependem de QUEM é o cliente — ``customer_segments``
        (grupo/RFM) e ``birthday_only`` — porque, se não batem, o desconto seria
        sempre 0. Restrições por item/contexto (``skus``, ``collections``,
        ``fulfillment_types``) NÃO são checadas aqui: elas só afetam QUAIS itens
        recebem desconto, não a elegibilidade do cliente ao cupom. Espelha a
        semântica de ``DiscountModifier._matches`` para esses dois eixos.

        ``customer`` é o cliente já resolvido do request (ou ``None`` para
        visitante anônimo).
        """
        from django.core.exceptions import ObjectDoesNotExist
        from django.utils import timezone as tz

        segments = list(getattr(promo, "customer_segments", None) or [])
        birthday_only = bool(getattr(promo, "birthday_only", False))
        if not segments and not birthday_only:
            return True  # cupom aberto a todos

        if customer is None:
            return False  # alvo exige identidade; visitante anônimo não qualifica

        if segments:
            group_ref = customer.group.ref if getattr(customer, "group_id", None) else ""
            try:
                rfm_segment = customer.insight.rfm_segment or ""
            except ObjectDoesNotExist:
                # Sem insight calculado (OneToOne ausente) o cliente so casa por
                # grupo; segmento RFM fica vazio. Degrada sem bloquear o cupom.
                logger.debug("coupon_eligibility_insight_missing")
                rfm_segment = ""
            if group_ref not in segments and rfm_segment not in segments:
                return False

        if birthday_only:
            birthday = getattr(customer, "birthday", None)
            if not birthday:
                return False
            today = tz.localdate()
            if not (birthday.month == today.month and birthday.day == today.day):
                return False

        return True

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

        from shopman.storefront.identity import get_authenticated_customer

        customer = get_authenticated_customer(request)

        # Alvo por QUEM é o cliente (segmento/grupo ou aniversário): se ele não se
        # qualifica, o DiscountModifier nunca aplicaria desconto (_matches falha).
        # Recusar no gate em vez de gravar um cupom mudo (desconto 0) no carrinho
        # sem aviso — ex.: FUNCIONARIO (customer_segments=["staff"]) para não-staff.
        if not CartService._customer_eligible_for_promo(customer, promo):
            return {"ok": False, "error": "coupon_not_eligible"}

        # Grava a identidade do cliente (ref + grupo) na sessão junto do cupom: um
        # cupom segmentado (ex.: "fiéis") só desconta se o DiscountModifier souber
        # o grupo/segmento do cliente — e ele resolve isso da sessão, a cada
        # reprice. Sem isto o cupom é aceito mas desconta zero.
        customer_payload = None
        if customer is not None:
            customer_payload = {
                "ref": getattr(customer, "ref", "") or "",
                "group": customer.group.ref if getattr(customer, "group_id", None) else "",
            }

        session = cart_mutations.apply_coupon_code(
            session_key=session_key,
            channel_ref=CHANNEL_REF,
            code=code,
            customer=customer_payload,
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

