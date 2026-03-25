from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View
from shopman.offering.models import Product

from ..cart import CartService
from ._helpers import _get_price_q


class CartView(View):
    """Full cart page."""

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        return render(request, "storefront/cart.html", {"cart": cart})


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
    """HTMX/JSON: apply a coupon code to the cart."""

    def post(self, request: HttpRequest) -> HttpResponse:
        code = request.POST.get("code", "").strip()
        if not code:
            return JsonResponse({"ok": False, "error": "empty_code"}, status=400)

        result = CartService.apply_coupon(request, code)
        status = 200 if result["ok"] else 400
        return JsonResponse(result, status=status)


class RemoveCouponView(View):
    """HTMX/JSON: remove coupon from the cart."""

    def post(self, request: HttpRequest) -> HttpResponse:
        result = CartService.remove_coupon(request)
        return JsonResponse(result)
