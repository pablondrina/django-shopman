from __future__ import annotations

from urllib.parse import urlparse

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django_ratelimit.decorators import ratelimit
from shopman.utils.monetary import format_money

from shopman.shop.services.cart import CartUnavailableError
from shopman.shop.services.storefront_context import minimum_order_progress
from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

from ..cart import CartService
from ..intents.cart import interpret_set_qty

MAX_CART_LINE_QTY = 99


def _parse_cart_qty(raw, *, minimum: int) -> int | None:
    try:
        qty = int(raw)
    except (TypeError, ValueError):
        return None
    if qty < minimum:
        qty = minimum
    return min(qty, MAX_CART_LINE_QTY)


def _rate_limited_cart_response() -> HttpResponse:
    return HttpResponse("", status=429)


def _money(value_q: int | None) -> str:
    return f"R$ {format_money(int(value_q or 0))}"


def _cart_command_payload(intent, cart: dict) -> dict:
    subtotal_q = int(cart.get("subtotal_q", 0) or 0)
    min_order = minimum_order_progress(
        subtotal_q,
        channel_ref=STOREFRONT_CHANNEL_REF,
    )
    line = _cart_line_payload(intent, cart)
    return {
        "ok": True,
        "action": intent.action,
        "sku": intent.sku,
        "line": line,
        "cart": {
            "count": int(cart.get("count", 0) or 0),
            "subtotal_q": subtotal_q,
            "subtotal_display": str(cart.get("subtotal_display") or _money(subtotal_q)),
            "grand_total_q": subtotal_q,
            "grand_total_display": str(cart.get("subtotal_display") or _money(subtotal_q)),
            "minimum_order_progress": min_order,
            "checkout_enabled": bool(cart.get("count", 0) and min_order is None),
        },
    }


def _cart_line_payload(intent, cart: dict) -> dict:
    line = next(
        (
            item
            for item in cart.get("items") or []
            if item.get("sku") == intent.sku
        ),
        None,
    )
    if line is None:
        return {
            "sku": intent.sku,
            "line_id": intent.line_id,
            "qty": 0,
            "unit_price_q": 0,
            "line_total_q": 0,
            "line_total_display": _money(0),
            "name": getattr(intent.product, "name", intent.sku),
        }

    qty = int(line.get("qty", 0) or 0)
    unit_price_q = int(line.get("unit_price_q", 0) or 0)
    line_total_q = int(line.get("line_total_q", 0) or 0)
    return {
        "sku": str(line.get("sku") or intent.sku),
        "line_id": line.get("line_id") or intent.line_id,
        "qty": qty,
        "unit_price_q": unit_price_q,
        "line_total_q": line_total_q,
        "line_total_display": _money(line_total_q),
        "name": line.get("name") or getattr(intent.product, "name", intent.sku),
    }


def _picker_origin(request: HttpRequest) -> str:
    """Which page is the modal being opened from.

    Drives the return flow (STOCK-UX-PLAN / WP-STOCK-UX-1b): picking an
    alternative from the PDP redirects to ``/cart/`` so the shopper sees
    the item they actually added; everywhere else stays in place.

    Reads HTMX's ``HX-Current-URL`` when present, with ``Referer`` as fallback
    for the fetch-based cart command.
    """
    current_url = (
        request.headers.get("HX-Current-URL")
        or request.META.get("HTTP_REFERER")
        or ""
    )
    path = urlparse(current_url).path
    if path.startswith("/produto/"):
        return "pdp"
    if path.startswith("/cart"):
        return "cart"
    return "menu"


class CartView(View):
    """Full cart page driven by ``CartProjection``."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.projections import build_cart

        cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        reorder_skipped = request.session.pop("reorder_skipped", None)
        from_reorder = request.session.pop("reorder_source", False)
        return render(request, "storefront/cart.html", {
            "cart": cart,
            "reorder_skipped": reorder_skipped,
            "from_reorder": from_reorder or bool(reorder_skipped),
        })


def _stock_error_response(request: HttpRequest, product, exc: CartUnavailableError) -> HttpResponse:
    """Render the kintsugi stock-error modal (3 variants: shortage/planned/paused)."""
    requested = int(exc.requested_qty)
    available = int(exc.available_qty)

    is_truly_paused = exc.is_paused or exc.error_code in {"paused", "not_in_listing"}
    if exc.is_planned and not is_truly_paused:
        error_variant = "planned"
    elif is_truly_paused:
        error_variant = "paused"
    else:
        error_variant = "shortage"

    primary_action = None
    primary_qty = 0
    if error_variant == "shortage" and available > 0:
        primary_action = "accept_available"
        primary_qty = available

    response = render(request, "storefront/partials/stock_error_modal.html", {
        "error_variant": error_variant,
        "sku": exc.sku,
        "product_name": product.name,
        "product_image_url": getattr(product, "image_url", None) or "",
        "requested_qty": requested,
        "available_qty": available,
        "substitutes": exc.substitutes,
        "error_code": exc.error_code,
        "is_paused": exc.is_paused,
        "is_planned": exc.is_planned,
        "planned_target_date": exc.planned_target_date,
        "primary_action": primary_action,
        "primary_qty": primary_qty,
        "picker_origin": _picker_origin(request),
    })
    response["HX-Retarget"] = "#stock-error-modal"
    response["HX-Reswap"] = "innerHTML"
    response["X-Shopman-Error-UI"] = "1"
    response.status_code = 422
    return response


class CartPageContentView(View):
    """HTMX: cart page inner content driven by ``CartProjection``.

    Companion to ``CartView``. Fetch-based item commands patch the visible
    line/summary directly; structural changes such as coupon updates or empty
    cart transitions still refetch this projection.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.projections import build_cart

        cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        return render(
            request,
            "storefront/partials/_cart_page_content.html",
            {"cart": cart},
        )


class CartDrawerContentProjView(View):
    """HTMX: cart drawer driven by ``CartProjection`` (typed projection)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF
        from shopman.storefront.projections import build_cart

        cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        return render(request, "storefront/partials/cart_drawer.html", {"cart": cart})


@method_decorator(ratelimit(key="user_or_ip", rate="120/m", method="POST", block=False), name="dispatch")
class CartSetQtyBySkuView(View):
    """Set absolute qty for a SKU and return a compact command response.

    Powers the inline stepper on catalog/PDP/cart controls: the client knows the SKU
    (not the Orderman ``line_id``) and pushes an absolute quantity each
    time the user taps ``+`` or ``−``. Resolves the open session line for
    the SKU and dispatches to ``CartService``:

    - qty ≤ 0  → ``remove_item`` if a line exists, otherwise no-op
    - qty > 0, line exists → ``update_qty`` (reconciles holds)
    - qty > 0, no line → ``add_item`` (adds with the current listing price)

    Success returns JSON only. Rich stock errors still return the existing
    server-rendered modal fragment because they are exceptional and should not
    duplicate kintsugi UX rules client-side.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        if getattr(request, "limited", False):
            return _rate_limited_cart_response()
        sku = request.POST.get("sku", "").strip()
        qty = _parse_cart_qty(request.POST.get("qty", 0), minimum=0)
        if qty is None:
            return HttpResponse("", status=400)

        cart = CartService.get_cart_summary(request, include_items=True)
        result = interpret_set_qty(sku, qty, cart)
        if result.error_type == "not_found":
            return HttpResponse("", status=404)

        intent = result.intent
        mutated_session = None
        try:
            if intent.action == "remove":
                if intent.line_id is not None:
                    mutated_session = CartService.remove_item(
                        request,
                        line_id=intent.line_id,
                        sku=intent.sku,
                    )
            elif intent.action == "update":
                mutated_session = CartService.update_qty(
                    request,
                    line_id=intent.line_id,
                    qty=intent.qty,
                    sku=intent.sku,
                )
            else:
                mutated_session = CartService.add_item(
                    request,
                    sku=intent.sku,
                    qty=intent.qty,
                    unit_price_q=intent.unit_price_q,
                    is_d1=intent.is_d1,
                )
        except CartUnavailableError as exc:
            return _stock_error_response(request, intent.product, exc)

        if mutated_session is not None:
            cart = CartService.summary_from_session(mutated_session, include_items=True)
        else:
            cart = CartService.get_cart_summary(request, include_items=True)
        response = JsonResponse(_cart_command_payload(intent, cart))
        return response


class CartSummaryView(View):
    """HTMX: return cart summary badge (triggered by cartUpdated event)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart_summary(request)
        return render(request, "storefront/partials/cart_summary.html", {"cart": cart})


@method_decorator(ratelimit(key="user_or_ip", rate="60/m", method="POST", block=False), name="dispatch")
class ApplyCouponView(View):
    """HTMX: apply a coupon code to the cart, return coupon section partial."""

    ERROR_MESSAGES = {
        "empty_code": "Informe o código do cupom.",
        "no_cart": "Carrinho vazio.",
        "invalid_coupon": "Cupom não encontrado.",
        "coupon_exhausted": "Este cupom já foi utilizado.",
        "coupon_expired": "Cupom expirado.",
    }

    def post(self, request: HttpRequest) -> HttpResponse:
        if getattr(request, "limited", False):
            return _rate_limited_cart_response()
        code = request.POST.get("code", "").strip()
        if not code:
            return self._notify(self.ERROR_MESSAGES["empty_code"], "warning")

        result = CartService.apply_coupon(request, code)
        if result["ok"]:
            cart = CartService.get_cart(request)
            coupon_info = cart.get("coupon")
            if coupon_info and coupon_info.get("discount_q", 0) == 0:
                CartService.remove_coupon(request)
                return self._notify(
                    "Você já tem um desconto melhor aplicado automaticamente.", "info"
                )
            response = HttpResponse("")
            response["HX-Trigger"] = "cartUpdated"
            return response

        error_key = result.get("error", "invalid_coupon")
        return self._notify(self.ERROR_MESSAGES.get(error_key, "Cupom inválido."), "warning")

    @staticmethod
    def _notify(message: str, variant: str) -> HttpResponse:
        import json

        response = HttpResponse("")
        response["HX-Trigger"] = json.dumps({"notify": {"variant": variant, "message": message}})
        return response


@method_decorator(ratelimit(key="user_or_ip", rate="60/m", method="POST", block=False), name="dispatch")
class RemoveCouponView(View):
    """HTMX: remove coupon from the cart; drawer reloads via cartUpdated."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if getattr(request, "limited", False):
            return _rate_limited_cart_response()
        CartService.remove_coupon(request)
        response = HttpResponse("")
        response["HX-Trigger"] = "cartUpdated"
        return response
