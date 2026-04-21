from __future__ import annotations

from urllib.parse import quote, urlparse

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View

from ..cart import CartService, CartUnavailableError
from ..intents.cart import interpret_add_to_cart, interpret_set_qty


def _picker_origin(request: HttpRequest) -> str:
    """Which page is the modal being opened from.

    Drives the return flow (STOCK-UX-PLAN / WP-STOCK-UX-1b): picking an
    alternative from the PDP redirects to ``/cart/`` so the shopper sees
    the item they actually added; everywhere else stays in place.

    Reads HTMX's ``HX-Current-URL`` (always sent for HTMX requests), with
    ``Referer`` as fallback.
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
        from shopman.storefront.projections import build_cart
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

        cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        return render(request, "storefront/cart.html", {"cart": cart})


class AddToCartView(View):
    """HTMX: add item to cart, return updated cart summary badge."""

    def post(self, request: HttpRequest) -> HttpResponse:
        sku = request.POST.get("sku", "").strip()
        qty = int(request.POST.get("qty", 1))
        if qty < 1:
            qty = 1

        result = interpret_add_to_cart(sku, qty, picker_origin=_picker_origin(request))
        if result.error_type == "not_found":
            return HttpResponse("", status=404)
        if result.error_type == "not_sellable":
            ctx = result.error_context
            response = render(request, "storefront/partials/stock_error_modal.html", {
                "error_variant": "paused",
                "sku": ctx["product"].sku,
                "product_name": ctx["product"].name,
                "product_image_url": getattr(ctx["product"], "image_url", None) or "",
                "requested_qty": ctx["qty"],
                "available_qty": 0,
                "substitutes": [],
                "picker_origin": ctx["picker_origin"],
            })
            response["HX-Retarget"] = "#stock-error-modal"
            response["HX-Reswap"] = "innerHTML"
            response["X-Shopman-Error-UI"] = "1"
            response.status_code = 422
            return response

        intent = result.intent
        try:
            CartService.add_item(
                request,
                sku=intent.sku,
                qty=intent.qty,
                unit_price_q=intent.unit_price_q,
                is_d1=intent.is_d1,
            )
        except CartUnavailableError as exc:
            return _stock_error_response(request, intent.product, exc)

        cart = CartService.get_cart(request)
        response = render(request, "storefront/partials/cart_summary.html", {"cart": cart})
        response["HX-Trigger"] = "cartUpdated"
        response["X-Cart-Item-Name"] = quote(intent.product.name, safe="")
        return response


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

    Companion to ``CartView`` — the page wraps the partial in a
    ``#cart-page-content`` div that listens for ``cartUpdated from:body``
    and refetches this URL, so stepper/delete/coupon/upsell actions
    refresh the cart in place without a full page reload.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        from shopman.storefront.projections import build_cart
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

        cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        return render(
            request,
            "storefront/partials/_cart_page_content.html",
            {"cart": cart},
        )


class CartDrawerContentProjView(View):
    """HTMX: cart drawer driven by ``CartProjection`` (typed read model)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from shopman.storefront.projections import build_cart
        from shopman.storefront.constants import STOREFRONT_CHANNEL_REF

        cart = build_cart(request=request, channel_ref=STOREFRONT_CHANNEL_REF)
        return render(request, "storefront/partials/cart_drawer.html", {"cart": cart})


class QuickAddView(View):
    """HTMX: quick-add from product card with inline stepper. SKU in path."""

    def post(self, request: HttpRequest, sku: str) -> HttpResponse:
        qty = int(request.POST.get("qty", 1))
        if qty < 1:
            qty = 1

        result = interpret_add_to_cart(sku, qty)
        if result.error_type == "not_found":
            return HttpResponse("", status=404)
        if result.error_type == "not_sellable":
            return HttpResponse("", status=409)

        intent = result.intent
        try:
            CartService.add_item(
                request,
                sku=intent.sku,
                qty=intent.qty,
                unit_price_q=intent.unit_price_q,
                is_d1=intent.is_d1,
            )
        except CartUnavailableError as exc:
            return _stock_error_response(request, intent.product, exc)

        cart = CartService.get_cart(request)
        response = render(request, "storefront/partials/cart_summary.html", {"cart": cart})
        response["HX-Trigger"] = "cartUpdated"
        response["X-Cart-Item-Name"] = quote(intent.product.name, safe="")
        return response


class CartSetQtyBySkuView(View):
    """HTMX: set absolute qty for a SKU, return cart summary badge.

    Powers the inline stepper on v2 catalog cards: the card knows the SKU
    (not the Orderman ``line_id``) and pushes an absolute quantity each
    time the user taps ``+`` or ``−``. Resolves the open session line for
    the SKU and dispatches to ``CartService``:

    - qty ≤ 0  → ``remove_item`` if a line exists, otherwise no-op
    - qty > 0, line exists → ``update_qty`` (reconciles holds)
    - qty > 0, no line → ``add_item`` (adds with the current listing price)

    Returns the same ``cart_summary`` partial + ``HX-Trigger: cartUpdated``
    as ``AddToCartView`` so the header badge and drawer stay in sync.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        sku = request.POST.get("sku", "").strip()
        try:
            qty = int(request.POST.get("qty", 0))
        except (TypeError, ValueError):
            qty = 0
        if qty < 0:
            qty = 0

        cart = CartService.get_cart(request)
        result = interpret_set_qty(sku, qty, cart)
        if result.error_type == "not_found":
            return HttpResponse("", status=404)

        intent = result.intent
        try:
            if intent.action == "remove":
                if intent.line_id is not None:
                    CartService.remove_item(request, line_id=intent.line_id)
            elif intent.action == "update":
                CartService.update_qty(request, line_id=intent.line_id, qty=intent.qty)
            else:
                CartService.add_item(
                    request,
                    sku=intent.sku,
                    qty=intent.qty,
                    unit_price_q=intent.unit_price_q,
                    is_d1=intent.is_d1,
                )
        except CartUnavailableError as exc:
            return _stock_error_response(request, intent.product, exc)

        cart = CartService.get_cart(request)
        response = render(request, "storefront/partials/cart_summary.html", {"cart": cart})
        response["HX-Trigger"] = "cartUpdated"
        response["X-Cart-Item-Name"] = quote(intent.product.name, safe="")
        return response


class CartSummaryView(View):
    """HTMX: return cart summary badge (triggered by cartUpdated event)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        return render(request, "storefront/partials/cart_summary.html", {"cart": cart})


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


class RemoveCouponView(View):
    """HTMX: remove coupon from the cart; drawer reloads via cartUpdated."""

    def post(self, request: HttpRequest) -> HttpResponse:
        CartService.remove_coupon(request)
        response = HttpResponse("")
        response["HX-Trigger"] = "cartUpdated"
        return response


