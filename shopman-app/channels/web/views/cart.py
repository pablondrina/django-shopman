from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views import View
from shopman.offering.models import Product
from shopman.utils.monetary import format_money

from ..cart import CHANNEL_REF, CartService
from ._helpers import _get_availability, _get_channel_listing_ref, _get_price_q, _min_order_progress, _upsell_suggestion


class CartView(View):
    """Redirect to menu — cart is now the drawer."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.urls import reverse

        return redirect(reverse("storefront:menu") + "?open_cart=1", permanent=False)


class AddToCartView(View):
    """HTMX: add item to cart, return updated cart summary badge."""

    def post(self, request: HttpRequest) -> HttpResponse:
        sku = request.POST.get("sku", "").strip()
        qty = int(request.POST.get("qty", 1))
        if qty < 1:
            qty = 1

        product = Product.objects.filter(sku=sku, is_published=True).first()
        if not product:
            return HttpResponse("", status=404)

        if not product.is_available:
            response = render(request, "storefront/partials/stock_error_modal.html", {
                "title": "Produto indisponível",
                "message": f"{product.name} não está disponível no momento. Confira outras opções no cardápio.",
            })
            response["HX-Retarget"] = "#stock-error-modal"
            response["HX-Reswap"] = "innerHTML"
            return response

        price_q = _get_price_q(product)
        if price_q is None:
            price_q = 0

        CartService.add_item(request, sku=sku, qty=qty, unit_price_q=price_q)
        cart = CartService.get_cart(request)
        response = render(request, "storefront/partials/cart_summary.html", {"cart": cart})
        response["HX-Trigger"] = "cartUpdated"
        return response


class CartDrawerContentView(View):
    """HTMX: return cart drawer content (items, subtotal, progress, upsell)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        ctx: dict = {"cart": cart}

        if cart["items"]:
            # Minimum order progress
            progress = _min_order_progress(cart["subtotal_q"])
            ctx["min_order_progress"] = progress

            # Upsell suggestion
            cart_skus = {item.get("sku", "") for item in cart["items"]}
            listing_ref = _get_channel_listing_ref()
            upsell = _upsell_suggestion(cart_skus, listing_ref=listing_ref)
            ctx["upsell"] = upsell

        return render(request, "storefront/partials/cart_drawer.html", ctx)


class QuickAddView(View):
    """HTMX: quick-add from product card with inline stepper. SKU in path."""

    def post(self, request: HttpRequest, sku: str) -> HttpResponse:
        qty = int(request.POST.get("qty", 1))
        if qty < 1:
            qty = 1

        product = Product.objects.filter(sku=sku, is_published=True).first()
        if not product:
            return HttpResponse("", status=404)
        if not product.is_available:
            return HttpResponse("", status=409)

        price_q = _get_price_q(product)
        if price_q is None:
            price_q = 0

        CartService.add_item(request, sku=sku, qty=qty, unit_price_q=price_q)
        cart = CartService.get_cart(request)
        response = render(request, "storefront/partials/cart_summary.html", {"cart": cart})
        response["HX-Trigger"] = "cartUpdated"
        return response


class UpdateCartItemView(View):
    """HTMX: update item qty, return updated cart item row + summary."""

    def post(self, request: HttpRequest) -> HttpResponse:
        line_id = request.POST.get("line_id", "").strip()
        qty = int(request.POST.get("qty", 1))
        if qty < 1:
            qty = 1

        CartService.update_qty(request, line_id=line_id, qty=qty)
        cart = CartService.get_cart(request)

        # Find the updated item
        item = next((i for i in cart["items"] if i["line_id"] == line_id), None)
        if not item:
            return HttpResponse("")

        response = render(request, "storefront/partials/cart_item.html", {"item": item})
        # Trigger cart summary update via HTMX event
        response["HX-Trigger"] = "cartUpdated"
        return response


class RemoveCartItemView(View):
    """HTMX: remove item from cart."""

    def post(self, request: HttpRequest) -> HttpResponse:
        line_id = request.POST.get("line_id", "").strip()
        CartService.remove_item(request, line_id=line_id)

        cart = CartService.get_cart(request)
        if not cart["items"]:
            response = render(request, "storefront/partials/cart_empty.html")
        else:
            response = HttpResponse("")
        response["HX-Trigger"] = "cartUpdated"
        return response


class CartContentPartialView(View):
    """HTMX: return cart content partial (items + subtotal + actions or empty state)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        return render(request, "storefront/partials/cart_content.html", {"cart": cart})


class CartSummaryView(View):
    """HTMX: return cart summary badge (triggered by cartUpdated event)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        return render(request, "storefront/partials/cart_summary.html", {"cart": cart})


class FloatingCartBarView(View):
    """HTMX partial: floating cart bar shown when cart is non-empty."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/partials/floating_cart_bar.html")


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
            return render(request, "storefront/partials/coupon_section.html", {
                "coupon_error": self.ERROR_MESSAGES["empty_code"],
            })

        result = CartService.apply_coupon(request, code)
        if result["ok"]:
            # Check if coupon actually won any item (maior desconto ganha)
            cart = CartService.get_cart(request)
            coupon_info = cart.get("coupon")
            if coupon_info and coupon_info.get("discount_q", 0) == 0:
                # Coupon lost to a better promo — remove it and inform user
                CartService.remove_coupon(request)
                return render(request, "storefront/partials/coupon_section.html", {
                    "coupon_error": "Você já tem um desconto melhor aplicado automaticamente.",
                })
            # Trigger drawer reload so breakdown/subtotal reflect the discount
            cart = CartService.get_cart(request)
            coupon_info = cart.get("coupon")
            response = render(request, "storefront/partials/coupon_section.html", {
                "coupon": coupon_info,
            })
            response["HX-Trigger"] = "cartUpdated"
            return response

        error_key = result.get("error", "invalid_coupon")
        return render(request, "storefront/partials/coupon_section.html", {
            "coupon_error": self.ERROR_MESSAGES.get(error_key, "Cupom inválido."),
        })


class RemoveCouponView(View):
    """HTMX: remove coupon from the cart, return coupon section partial."""

    def post(self, request: HttpRequest) -> HttpResponse:
        CartService.remove_coupon(request)
        # Return empty coupon section + trigger drawer reload
        response = render(request, "storefront/partials/coupon_section.html", {
            "coupon": None,
        })
        response["HX-Trigger"] = "cartUpdated"
        return response


class CartCheckView(View):
    """HTMX: revalidate stock for all cart items, return warnings."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from decimal import Decimal

        cart = CartService.get_cart(request)
        items = cart.get("items", [])
        if not items:
            return render(request, "storefront/partials/cart_warnings.html", {"warnings": []})

        warnings = []
        skus = [item.get("sku", "") for item in items if item.get("sku")]
        product_names = dict(
            Product.objects.filter(sku__in=skus).values_list("sku", "name")
        ) if skus else {}

        # Get qty held by this session's own holds so we don't double-count.
        # _get_availability() returns stock MINUS active holds. If this session
        # already has holds for these SKUs, available_qty is artificially low.
        session_held = _get_session_held_qty(request)

        for item in items:
            sku = item.get("sku", "")
            qty = int(Decimal(str(item.get("qty", 0))))
            avail = _get_availability(sku)
            if avail is None:
                continue
            breakdown = avail.get("breakdown", {})
            ready = breakdown.get("ready", Decimal("0"))
            in_prod = breakdown.get("in_production", Decimal("0"))
            d1 = breakdown.get("d1", Decimal("0"))
            available_qty = int(ready + in_prod + d1)

            # Add back what this session holds — it's our own reservation.
            available_qty += session_held.get(sku, 0)

            if qty > available_qty:
                warnings.append({
                    "line_id": item.get("line_id", ""),
                    "name": product_names.get(sku, sku),
                    "sku": sku,
                    "requested_qty": qty,
                    "available_qty": available_qty,
                })

        return render(request, "storefront/partials/cart_warnings.html", {"warnings": warnings})


def _get_session_held_qty(request: HttpRequest) -> dict[str, int]:
    """Get qty held per SKU by the current session's active stock holds."""
    session_key = request.session.get("cart_session_key")
    if not session_key:
        return {}
    try:
        from shopman.stocking.models import Hold

        holds = Hold.objects.filter(
            metadata__reference=session_key,
        ).active()

        held: dict[str, int] = {}
        for h in holds:
            held[h.sku] = held.get(h.sku, 0) + int(h.quantity)
        return held
    except (ImportError, Exception):
        return {}
