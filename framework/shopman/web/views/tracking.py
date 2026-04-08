"""Order tracking views — tracking page, status partial, reorder, cancel, CEP lookup, confirmation."""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views import View

from shopman.omniman.models import Order
from shopman.utils.monetary import format_money

from ..cart import CartService
from ._helpers import _carrier_tracking_url, _format_opening_hours, _get_price_q, _line_item_is_d1

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    "new": "Recebido",
    "confirmed": "Confirmado",
    "preparing": "Em Preparo",
    "ready": "Pronto",
    "dispatched": "Saiu para entrega",
    "delivered": "Entregue",
    "completed": "Concluído",
    "cancelled": "Cancelado",
    "returned": "Devolvido",
}

STATUS_COLORS = {
    "new": "bg-info-light text-foreground border border-info/30",
    "confirmed": "bg-info-light text-foreground border border-info/30",
    "preparing": "bg-warning-light text-warning-foreground border border-warning/40",
    "ready": "bg-success-light text-foreground border border-success/30",
    "dispatched": "bg-info-light text-foreground border border-info/30",
    "delivered": "bg-success-light text-foreground border border-success/30",
    "completed": "bg-success-light text-foreground border border-success/30",
    "cancelled": "bg-error-light text-foreground border border-error/30",
    "returned": "bg-muted text-muted-foreground",
}

FULFILLMENT_STATUS_LABELS = {
    "pending": "Aguardando",
    "in_progress": "Em separação",
    "dispatched": "Saiu para entrega",
    "delivered": "Entregue",
    "cancelled": "Cancelado",
}

EVENT_LABELS = {
    "created": "Pedido criado",
    "status_changed": None,
    "payment.captured": "Pagamento confirmado",
    "payment.refunded": "Pagamento estornado",
    "return_initiated": "Devolução solicitada",
    "refund_processed": "Reembolso processado",
    "fiscal_cancelled": "Nota fiscal cancelada",
    "fulfillment.dispatched": "Saiu para entrega",
    "fulfillment.delivered": "Pedido entregue",
}

_CANCELLABLE_STATUSES = {Order.Status.NEW, Order.Status.CONFIRMED}
_TERMINAL_STATUSES = {"completed", "cancelled", "returned"}


def _pickup_info() -> dict | None:
    """Load store address and opening hours for pickup fulfillments."""
    try:
        from shopman.models import Shop

        shop = Shop.load()
        if not shop:
            return None
        return {
            "address": shop.formatted_address or "",
            "opening_hours": _format_opening_hours(),
        }
    except Exception as e:
        logger.warning("pickup_info_failed: %s", e, exc_info=True)
        return None


def _get_effective_config(channel) -> dict:
    """Build effective config: defaults <- shop <- channel (flat dict merge)."""
    from shopman.models import Shop

    base = {}
    shop = Shop.load()
    if shop and shop.defaults:
        base.update(shop.defaults)
    if channel and channel.config:
        base.update(channel.config)
    return base


def _build_tracking_context(order: Order) -> dict:
    """Build shared context for tracking page and status partial."""
    events = order.events.order_by("seq")
    timeline = []
    for event in events:
        payload = event.payload or {}
        status_key = payload.get("new_status", "")

        if event.type == "status_changed" and status_key:
            label = STATUS_LABELS.get(status_key, status_key)
        else:
            label = EVENT_LABELS.get(event.type)
            if label is None:
                label = event.type.replace(".", " ").replace("_", " ").title()

        timeline.append({
            "label": label,
            "type": event.type,
            "timestamp": event.created_at,
            "payload": payload,
            "icon": STATUS_ICONS.get(status_key, ""),
        })

    items = []
    for item in order.items.all():
        items.append({
            "sku": item.sku,
            "name": item.name or item.sku,
            "qty": item.qty,
            "unit_price_display": f"R$ {format_money(item.unit_price_q)}",
            "total_display": f"R$ {format_money(item.line_total_q)}",
        })

    delivery_fulfillments = []
    pickup_fulfillments = []
    for ful in order.fulfillments.all():
        tracking_url = ful.tracking_url or _carrier_tracking_url(ful.carrier, ful.tracking_code)
        entry = {
            "id": ful.pk,
            "status": ful.status,
            "status_label": FULFILLMENT_STATUS_LABELS.get(ful.status, ful.status),
            "tracking_code": ful.tracking_code,
            "tracking_url": tracking_url,
            "carrier": ful.carrier,
            "dispatched_at": ful.dispatched_at,
            "delivered_at": ful.delivered_at,
        }
        if ful.carrier or ful.tracking_code:
            delivery_fulfillments.append(entry)
        else:
            pickup_fulfillments.append(entry)

        if ful.dispatched_at:
            timeline.append({
                "label": "Enviado",
                "type": "fulfillment.dispatched",
                "timestamp": ful.dispatched_at,
                "payload": {},
            })
        if ful.delivered_at:
            timeline.append({
                "label": "Entregue",
                "type": "fulfillment.delivered",
                "timestamp": ful.delivered_at,
                "payload": {},
            })

    timeline.sort(key=lambda e: e["timestamp"])

    pickup = _pickup_info() if pickup_fulfillments else None

    payment = order.data.get("payment", {})
    payment_captured = payment.get("status") == "captured"
    can_cancel = (
        order.status in _CANCELLABLE_STATUSES
        and not payment_captured
    )

    is_active = order.status not in _TERMINAL_STATUSES

    confirmation_countdown = False
    confirmation_expires_at = None
    if order.status == "new":
        config = _get_effective_config(order.channel)
        confirmation_mode = config.get("confirmation", {}).get("mode", "immediate") if isinstance(config.get("confirmation"), dict) else config.get("confirmation_mode", "immediate")
        if confirmation_mode == "optimistic":
            from datetime import timedelta
            confirmation_countdown = True
            timeout = config.get("confirmation", {}).get("timeout_minutes", 5) if isinstance(config.get("confirmation"), dict) else config.get("confirmation_timeout_minutes", 5)
            confirmation_expires_at = order.created_at + timedelta(minutes=timeout)

    eta = None
    if order.status == "preparing":
        from django.utils import timezone as tz

        from shopman.models import Shop
        shop = Shop.load()
        prep_minutes = getattr(shop, "prep_time_minutes", None) or 30
        eta = tz.localtime(order.created_at) + tz.timedelta(minutes=prep_minutes)

    order_data = order.data or {}

    # Delivery fee from order.data (propagated by CommitService)
    delivery_fee_q = order_data.get("delivery_fee_q")
    delivery_fee_display = None
    if delivery_fee_q is not None:
        delivery_fee_display = "Grátis" if delivery_fee_q == 0 else f"R$ {format_money(delivery_fee_q)}"

    # Item #3: contextual "ready" label — pickup vs delivery
    # Item #6: completed is invisible to customer (shows "Entregue" for delivery, "Concluído" for pickup)
    fulfillment_type = order_data.get("fulfillment_type") or order_data.get("delivery_method", "")
    is_delivery = fulfillment_type == "delivery"

    status_label = STATUS_LABELS.get(order.status, order.status)
    if order.status == "ready":
        status_label = "Aguardando motoboy" if is_delivery else "Pronto para retirada"
    elif order.status == "completed":
        status_label = "Entregue" if is_delivery else "Concluído"

    return {
        "order": order,
        "status_label": status_label,
        "status_color": STATUS_COLORS.get(order.status, "bg-muted text-muted-foreground"),
        "timeline": timeline,
        "items": items,
        "total_display": f"R$ {format_money(order.total_q)}",
        "delivery_fee_q": delivery_fee_q,
        "delivery_fee_display": delivery_fee_display,
        "delivery_fulfillments": delivery_fulfillments,
        "pickup_fulfillments": pickup_fulfillments,
        "pickup": pickup,
        "can_cancel": can_cancel,
        "is_active": is_active,
        "confirmation_countdown": confirmation_countdown,
        "confirmation_expires_at": confirmation_expires_at,
        "eta": eta,
    }


class OrderTrackingView(View):
    """Full order tracking page with HTMX polling for status updates."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        ctx = _build_tracking_context(order)

        from shopman.models import Shop
        shop = Shop.load()
        whatsapp_url = ""
        if shop:
            for link in (shop.social_links or []):
                if "wa.me" in link or "whatsapp.com" in link:
                    whatsapp_url = link
                    break
            if not whatsapp_url and shop.phone:
                digits = "".join(c for c in shop.phone if c.isdigit())
                whatsapp_url = f"https://wa.me/{digits}"

        share_text = f"Meu pedido {order.ref} na {shop.name if shop else 'loja'}"

        ctx["whatsapp_url"] = whatsapp_url
        ctx["share_text"] = share_text
        return render(request, "storefront/tracking.html", ctx)


STATUS_ICONS = {
    "new": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M5 3a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2V5a2 2 0 00-2-2H5zm0 2h10v7h-2l-1 2H8l-1-2H5V5z" clip-rule="evenodd"/></svg>',
    "confirmed": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>',
    "preparing": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M11.49 3.17c-.38-1.56-2.6-1.56-2.98 0a1.532 1.532 0 01-2.286.948c-1.372-.836-2.942.734-2.106 2.106.54.886.061 2.042-.947 2.287-1.561.379-1.561 2.6 0 2.978a1.532 1.532 0 01.947 2.287c-.836 1.372.734 2.942 2.106 2.106a1.532 1.532 0 012.287.947c.379 1.561 2.6 1.561 2.978 0a1.533 1.533 0 012.287-.947c1.372.836 2.942-.734 2.106-2.106a1.533 1.533 0 01.947-2.287c1.561-.379 1.561-2.6 0-2.978a1.532 1.532 0 01-.947-2.287c.836-1.372-.734-2.942-2.106-2.106a1.532 1.532 0 01-2.287-.947zM10 13a3 3 0 100-6 3 3 0 000 6z" clip-rule="evenodd"/></svg>',
    "ready": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>',
    "dispatched": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M8 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0zM15 16.5a1.5 1.5 0 11-3 0 1.5 1.5 0 013 0z"/><path d="M0 4a1 1 0 011-1h11a1 1 0 011 1v1h2.38l2.45 3.26A1 1 0 0118 9v3a1 1 0 01-1 1h-1.05a2.5 2.5 0 00-4.9 0H8.95a2.5 2.5 0 00-4.9 0H3a1 1 0 01-1-1V5H1a1 1 0 01-1-1z"/></svg>',
    "delivered": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path d="M10.707 2.293a1 1 0 00-1.414 0l-7 7a1 1 0 001.414 1.414L4 10.414V17a1 1 0 001 1h2a1 1 0 001-1v-2a1 1 0 011-1h2a1 1 0 011 1v2a1 1 0 001 1h2a1 1 0 001-1v-6.586l.293.293a1 1 0 001.414-1.414l-7-7z"/></svg>',
    "completed": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>',
    "cancelled": '<svg class="w-4 h-4" viewBox="0 0 20 20" fill="currentColor"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>',
}


class ReorderView(View):
    """POST: re-add all items from a past order to the cart."""

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        from shopman.offerman.models import Product
        from shopman.web.cart import CartUnavailableError

        order = get_object_or_404(Order, ref=ref)
        skipped: list[str] = []
        for item in order.items.all():
            product = Product.objects.filter(sku=item.sku, is_published=True).first()
            if product and product.is_available:
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
                # Product unavailable/unpublished — collect for UX feedback
                name = product.name if product else item.sku
                skipped.append(name)

        if skipped:
            request.session["reorder_skipped"] = skipped

        return redirect("storefront:cart")


class OrderStatusPartialView(View):
    """HTMX partial: returns status badge + timeline for polling."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        ctx = _build_tracking_context(order)
        response = render(request, "storefront/partials/order_status.html", ctx)
        if order.status in _TERMINAL_STATUSES:
            response.status_code = 286
        return response


class OrderCancelView(View):
    """Customer self-service cancellation from tracking page.

    Uses services.cancellation.cancel() — the Flow.on_cancelled()
    handler releases stock, refunds payment, and sends notifications.
    """

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        from shopman.services.cancellation import cancel

        order = get_object_or_404(Order, ref=ref)

        payment_status = order.data.get("payment", {}).get("status", "")
        if order.status not in _CANCELLABLE_STATUSES:
            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '<div class="toast toast-error" role="alert" aria-live="assertive">'
                    "Não é possível cancelar este pedido no status atual.</div>",
                    status=422,
                )
            return redirect("storefront:order_tracking", ref=ref)

        if payment_status == "captured":
            if request.headers.get("HX-Request"):
                return HttpResponse(
                    '<div class="toast toast-warning" role="alert" aria-live="assertive">'
                    "Pagamento já confirmado. Entre em contato para cancelar.</div>",
                    status=422,
                )
            return redirect("storefront:order_tracking", ref=ref)

        cancel(order, reason="customer_requested", actor="customer.self_cancel")

        logger.info("customer_self_cancel order=%s", order.ref)

        if request.headers.get("HX-Request"):
            ctx = _build_tracking_context(order)
            return render(request, "storefront/partials/order_status.html", ctx)
        return redirect("storefront:order_tracking", ref=ref)


class CepLookupView(View):
    """HTMX: lookup address by CEP via ViaCEP API."""

    def get(self, request: HttpRequest) -> HttpResponse:
        import json
        import urllib.request

        cep = (request.GET.get("cep") or request.GET.get("cep_sheet", "")).strip().replace("-", "").replace(".", "")
        if not cep or len(cep) != 8 or not cep.isdigit():
            return HttpResponse(
                '<p class="text-error text-xs mt-1">CEP inv\u00e1lido (8 d\u00edgitos)</p>',
            )

        try:
            url = f"https://viacep.com.br/ws/{cep}/json/"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())

            if data.get("erro"):
                return HttpResponse(
                    '<p class="text-error text-xs mt-1">CEP n\u00e3o encontrado</p>',
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
        except Exception as e:
            logger.warning("cep_lookup_failed cep=%s: %s", cep, e, exc_info=True)
            return HttpResponse(
                '<p class="text-warning text-xs mt-1">N\u00e3o foi poss\u00edvel buscar o CEP. Preencha manualmente.</p>',
            )


class OrderConfirmationView(View):
    """Order confirmation page — celebration for immediate-confirmation channels."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)

        channel = order.channel
        if channel:
            config = _get_effective_config(channel)
            confirmation_mode = config.get("confirmation", {}).get("mode", "immediate") if isinstance(config.get("confirmation"), dict) else config.get("confirmation_mode", "immediate")
            if confirmation_mode == "optimistic":
                return redirect("storefront:order_tracking", ref=ref)

        items = order.items.all()

        enriched_items = []
        for item in items:
            enriched_items.append({
                "sku": item.sku,
                "name": item.name or item.sku,
                "qty": item.qty,
                "unit_price_display": f"R$ {format_money(item.unit_price_q)}",
                "total_display": f"R$ {format_money(item.line_total_q)}",
            })

        tracking_path = f"/pedido/{order.ref}/"
        share_url = request.build_absolute_uri(tracking_path)

        from django.utils import timezone

        from shopman.models import Shop
        shop = Shop.load()
        prep_minutes = getattr(shop, "prep_time_minutes", None) or 30
        eta = timezone.localtime(order.created_at) + timezone.timedelta(minutes=prep_minutes)

        return render(request, "storefront/order_confirmation.html", {
            "order": order,
            "items": enriched_items,
            "total_display": f"R$ {format_money(order.total_q)}",
            "share_url": share_url,
            "eta": eta,
        })
