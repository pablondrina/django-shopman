"""Order tracking views — tracking page, status partial, reorder, cancel, CEP lookup, confirmation."""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from ..cart import CartService
from ..services import orders as order_service
from ._helpers import _get_price_q, _line_item_is_d1

logger = logging.getLogger(__name__)


class OrderTrackingView(View):
    """Full order tracking page with HTMX polling for status updates."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = order_service.get_order(ref)

        from shopman.storefront.projections import build_order_tracking

        proj = build_order_tracking(order)
        ctx: dict = {"tracking": proj}
        if request.GET.get("refused"):
            ctx["cancel_refused"] = True
        return render(request, "storefront/order_tracking.html", ctx)


class ReorderView(View):
    """POST: re-add all items from a past order to the cart."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        from shopman.offerman.models import Product

        from shopman.storefront.cart import CartUnavailableError

        order = order_service.get_order(ref)
        skipped: list[str] = []
        for item in order.items.all():
            product = Product.objects.filter(sku=item.sku, is_published=True).first()
            if product and product.is_sellable:
                price_q = _get_price_q(product)
                if price_q is None:
                    price_q = 0
                try:
                    CartService.add_item(
                        request,
                        sku=item.sku,
                        qty=int(item.qty),
                        unit_price_q=price_q,
                        is_d1=_line_item_is_d1(product),
                    )
                except CartUnavailableError:
                    skipped.append(product.name or item.sku)
            else:
                name = product.name if product else item.sku
                skipped.append(name)

        request.session["reorder_source"] = True
        if skipped:
            request.session["reorder_skipped"] = skipped

        return redirect("storefront:cart")


class OrderStatusPartialView(View):
    """HTMX partial: returns status badge + timeline for polling."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = order_service.get_order(ref)

        from shopman.storefront.projections import build_order_tracking_status

        proj = build_order_tracking_status(order)
        response = render(
            request, "storefront/partials/order_status.html", {"tracking_status": proj}
        )
        if proj.is_terminal:
            response.status_code = 286
        return response


class OrderCancelView(View):
    """Customer self-service cancellation from tracking page."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = order_service.get_order(ref)

        if not order_service.can_cancel(order):
            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '<div class="toast toast-error" role="alert" aria-live="assertive">'
                    "Não é possível cancelar este pedido no status atual.</div>",
                    status=422,
                )
            return HttpResponseRedirect(
                reverse("storefront:order_tracking", kwargs={"ref": ref}) + "?refused=1"
            )

        if order_service.payment_status(order) == "captured":
            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '<div class="toast toast-warning" role="alert" aria-live="assertive">'
                    "Pagamento já confirmado. Entre em contato para cancelar.</div>",
                    status=422,
                )
            return HttpResponseRedirect(
                reverse("storefront:order_tracking", kwargs={"ref": ref}) + "?refused=1"
            )

        order_service.cancel(order)

        logger.info("customer_self_cancel order=%s", order.ref)

        if request.headers.get("HX-Request"):
            from shopman.storefront.projections import build_order_tracking_status

            proj = build_order_tracking_status(order)
            return render(
                request, "storefront/partials/order_status.html", {"tracking_status": proj}
            )
        return redirect("storefront:order_tracking", ref=ref)


class CepLookupView(View):
    """HTMX: lookup address by CEP via ViaCEP API."""

    def get(self, request: HttpRequest) -> HttpResponse:
        import json
        import urllib.request

        cep = (request.GET.get("cep") or request.GET.get("cep_sheet", "")).strip().replace("-", "").replace(".", "")
        if not cep or len(cep) != 8 or not cep.isdigit():
            return HttpResponse(
                '<p class="text-warning text-xs mt-1">CEP precisa de 8 d\u00edgitos. Confira e tente de novo.</p>',
            )

        try:
            url = f"https://viacep.com.br/ws/{cep}/json/"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())

            if data.get("erro"):
                return HttpResponse(
                    '<p class="text-warning text-xs mt-1">N\u00e3o encontrei esse CEP. Quer digitar o endere\u00e7o manualmente?</p>',
                )

            logradouro = data.get("logradouro", "")
            bairro = data.get("bairro", "")
            cidade = data.get("localidade", "")
            uf = data.get("uf", "")

            parts = [p for p in [logradouro, bairro, f"{cidade}/{uf}"] if p]
            address_str = ", ".join(parts)

            dispatch_data = json.dumps({
                "route": logradouro,
                "neighborhood": bairro,
                "city": cidade,
                "stateCode": uf,
                "postalCode": f"{cep[:5]}-{cep[5:]}",
            }, ensure_ascii=False)

            return HttpResponse(
                f'<div class="text-success-foreground text-xs mt-1 flex items-center gap-1"'
                f" x-data x-init=\"$dispatch('cep-found', {dispatch_data})\">"
                f'<svg class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>'
                f'{address_str}</div>',
            )
        except Exception:
            logger.exception("cep_lookup_failed cep=%s", cep)
            return HttpResponse(
                '<p class="text-warning text-xs mt-1">N\u00e3o foi poss\u00edvel buscar o CEP. Preencha manualmente.</p>',
            )


class OrderConfirmationView(View):
    """Order confirmation page — shown after checkout for manual-confirm channels."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = order_service.get_order(ref)

        if order_service.should_skip_confirmation(order):
            return redirect("storefront:order_tracking", ref=ref)

        from shopman.storefront.projections import build_order_confirmation

        tracking_path = f"/pedido/{order.ref}/"
        share_url = request.build_absolute_uri(tracking_path)
        confirmation = build_order_confirmation(order, share_url=share_url)

        return render(request, "storefront/order_confirmation.html", {"confirmation": confirmation})
