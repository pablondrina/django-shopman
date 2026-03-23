from __future__ import annotations

from datetime import timedelta

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_POST

from shopman.utils.monetary import format_money
from shopman.utils.phone import normalize_phone
from shopman.offering.models import Collection, CollectionItem, ListingItem, Product
from shopman.ordering.ids import generate_idempotency_key
from shopman.ordering.models import Channel, Order, OrderEvent
from shopman.ordering.services.commit import CommitService

from .cart import CHANNEL_CODE, CartService

DEFAULT_DDD = "43"  # Londrina — Nelson Boulangerie

# Check if doorman is available for inline auth
try:
    from django.apps import apps as _apps

    _apps.get_app_config("shopman.gating")
    HAS_DOORMAN = True
except LookupError:
    HAS_DOORMAN = False

# Check if stockman availability API is available
try:
    from shopman.stocking.api.views import _availability_for_sku, _get_safety_margin

    HAS_STOCKMAN = True
except ImportError:
    HAS_STOCKMAN = False

LISTING_CODES = ("balcao", "whatsapp")
STOREFRONT_CHANNEL_REF = "web"


# ── Customer Lookup ──────────────────────────────────────────────


class CustomerLookupView(View):
    """HTMX/JSON: lookup customer by phone, return name + saved addresses."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.http import JsonResponse

        phone_raw = request.GET.get("phone", "").strip()
        if not phone_raw:
            return JsonResponse({"found": False})

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            return JsonResponse({"found": False})

        # Check if already verified in this session
        verified_phone = request.session.get("storefront_verified_phone")
        is_verified = verified_phone == phone

        from shopman.attending.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)
        if not customer:
            return JsonResponse({"found": False, "can_verify": False})

        addresses = []
        for addr in customer.addresses.order_by("-is_default", "label"):
            addresses.append({
                "id": addr.id,
                "label": addr.display_label,
                "formatted_address": addr.formatted_address,
                "complement": addr.complement or "",
                "delivery_instructions": addr.delivery_instructions or "",
                "is_default": addr.is_default,
            })

        return JsonResponse({
            "found": True,
            "name": customer.name,
            "phone": customer.phone,
            "addresses": addresses,
            "can_verify": HAS_DOORMAN and not is_verified,
            "is_verified": is_verified,
        })


def _get_price_q(product: Product) -> int | None:
    """Get price from first available listing, falling back to base_price_q."""
    for code in LISTING_CODES:
        item = (
            ListingItem.objects.filter(
                listing__code=code,
                listing__is_active=True,
                product=product,
                is_published=True,
                is_available=True,
            )
            .order_by("-listing__priority")
            .first()
        )
        if item:
            return item.price_q
    return product.base_price_q


def _get_availability(sku: str) -> dict | None:
    """Get availability breakdown for a SKU. Returns None if stockman unavailable."""
    if not HAS_STOCKMAN:
        return None
    try:
        margin = _get_safety_margin(STOREFRONT_CHANNEL_REF)
        return _availability_for_sku(sku, safety_margin=margin)
    except Exception:
        return None


def _availability_badge(avail: dict | None, product: Product) -> dict:
    """
    Determine the availability badge for a product.

    Returns dict with keys: label, css_class, can_add_to_cart.
    Possible states:
    - available: ready stock > 0
    - preparing: no ready stock, but in_production > 0
    - d1_only: only D-1 stock (yesterday's leftovers)
    - sold_out: no stock at all
    - paused: product marked unavailable by admin
    - unknown: stockman unavailable (fall back to product.is_available)
    """
    if not product.is_available:
        return {"label": "Indisponível", "css_class": "badge-paused", "can_add_to_cart": False}

    if avail is None:
        # No stockman — fall back to product.is_available flag
        return {"label": "", "css_class": "", "can_add_to_cart": product.is_available}

    if avail.get("is_paused"):
        return {"label": "Indisponível", "css_class": "badge-paused", "can_add_to_cart": False}

    breakdown = avail.get("breakdown", {})
    from decimal import Decimal

    ready = breakdown.get("ready", Decimal("0"))
    in_prod = breakdown.get("in_production", Decimal("0"))
    d1 = breakdown.get("d1", Decimal("0"))

    if ready > 0:
        return {"label": "Disponível", "css_class": "badge-available", "can_add_to_cart": True}
    if in_prod > 0:
        return {"label": "Preparando...", "css_class": "badge-preparing", "can_add_to_cart": True}
    if d1 > 0:
        return {"label": "Últimas unidades", "css_class": "badge-d1", "can_add_to_cart": True}
    if avail.get("is_planned"):
        return {"label": "Em breve", "css_class": "badge-planned", "can_add_to_cart": False}
    return {"label": "Esgotado", "css_class": "badge-sold-out", "can_add_to_cart": False}


def _annotate_products(products: list[Product]) -> list[dict]:
    """Build template-ready list with price, availability, and D-1 info."""
    result = []
    for p in products:
        price_q = _get_price_q(p)
        avail = _get_availability(p.sku)
        badge = _availability_badge(avail, p)

        # D-1 discount: 50% off if only D-1 stock
        d1_price_q = None
        d1_price_display = None
        is_d1 = False
        if avail and badge["css_class"] == "badge-d1" and price_q:
            is_d1 = True
            d1_price_q = price_q // 2
            d1_price_display = f"R$ {format_money(d1_price_q)}"

        result.append({
            "product": p,
            "price_q": d1_price_q if is_d1 else price_q,
            "price_display": f"R$ {format_money(price_q)}" if price_q else None,
            "d1_price_display": d1_price_display,
            "original_price_display": f"R$ {format_money(price_q)}" if is_d1 and price_q else None,
            "is_d1": is_d1,
            "badge": badge,
            "availability": avail,
        })
    return result


@method_decorator(ensure_csrf_cookie, name="dispatch")
class MenuView(View):
    """List products grouped by collection."""

    def get(self, request: HttpRequest, collection: str | None = None) -> HttpResponse:
        collections = Collection.objects.filter(is_active=True).order_by("sort_order", "name")
        active_collection = None

        if collection:
            active_collection = get_object_or_404(Collection, slug=collection, is_active=True)
            products = (
                Product.objects.filter(
                    is_published=True,
                    collection_items__collection=active_collection,
                )
                .order_by("collection_items__sort_order", "name")
                .distinct()
            )
            sections = [{"collection": active_collection, "products": _annotate_products(list(products))}]
        else:
            sections = []
            for col in collections:
                products = (
                    Product.objects.filter(
                        is_published=True,
                        collection_items__collection=col,
                    )
                    .order_by("collection_items__sort_order", "name")
                    .distinct()
                )
                if products.exists():
                    sections.append({"collection": col, "products": _annotate_products(list(products))})

            # Products not in any collection
            uncategorized = (
                Product.objects.filter(is_published=True)
                .exclude(collection_items__isnull=False)
                .order_by("name")
            )
            if uncategorized.exists():
                sections.append({
                    "collection": None,
                    "products": _annotate_products(list(uncategorized)),
                })

        return render(request, "storefront/menu.html", {
            "sections": sections,
            "collections": collections,
            "active_collection": active_collection,
        })


class MenuSearchView(View):
    """HTMX partial: search products by name."""

    def get(self, request: HttpRequest) -> HttpResponse:
        q = request.GET.get("q", "").strip()
        if len(q) < 2:
            if q:
                return render(request, "storefront/partials/search_results.html", {
                    "items": [],
                    "query": q,
                    "hint": True,
                })
            return HttpResponse("")

        products = Product.objects.filter(
            is_published=True,
            name__icontains=q,
        ).order_by("name")[:20]

        items = _annotate_products(list(products))
        return render(request, "storefront/partials/search_results.html", {
            "items": items,
            "query": q,
        })


class ProductDetailView(View):
    """Product detail page."""

    def get(self, request: HttpRequest, sku: str) -> HttpResponse:
        product = get_object_or_404(Product, sku=sku, is_published=True)
        price_q = _get_price_q(product)
        avail = _get_availability(product.sku)
        badge = _availability_badge(avail, product)

        # D-1 discount
        d1_price_display = None
        original_price_display = None
        is_d1 = False
        if avail and badge["css_class"] == "badge-d1" and price_q:
            is_d1 = True
            d1_price_q = price_q // 2
            d1_price_display = f"R$ {format_money(d1_price_q)}"
            original_price_display = f"R$ {format_money(price_q)}"
            price_q = d1_price_q

        return render(request, "storefront/product_detail.html", {
            "product": product,
            "price_q": price_q,
            "price_display": f"R$ {format_money(price_q)}" if price_q else None,
            "d1_price_display": d1_price_display,
            "original_price_display": original_price_display,
            "is_d1": is_d1,
            "badge": badge,
            "availability": avail,
        })


# ── Cart Views ───────────────────────────────────────────────────────


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


# ── Checkout Views ───────────────────────────────────────────────────


@method_decorator(ensure_csrf_cookie, name="dispatch")
class CheckoutView(View):
    """Checkout: review order and submit."""

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        if not cart["items"]:
            return redirect("storefront:cart")

        ctx: dict = {"cart": cart}

        # Pre-fill from verified session
        verified_phone = request.session.get("storefront_verified_phone")
        if verified_phone:
            verified_name = request.session.get("storefront_verified_name", "")
            ctx["form_data"] = {"phone": verified_phone, "name": verified_name}
            ctx["is_verified"] = True

        return render(request, "storefront/checkout.html", ctx)

    def post(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        if not cart["items"]:
            return redirect("storefront:cart")

        name = request.POST.get("name", "").strip()
        phone_raw = request.POST.get("phone", "").strip()
        notes = request.POST.get("notes", "").strip()

        errors = {}
        if not name:
            errors["name"] = "Nome é obrigatório."
        if not phone_raw:
            errors["phone"] = "Telefone é obrigatório."
        else:
            try:
                phone = normalize_phone(phone_raw)
                if not phone:
                    # Try with default DDD (Londrina)
                    digits = "".join(c for c in phone_raw if c.isdigit())
                    if 8 <= len(digits) <= 9:
                        phone = normalize_phone(f"{DEFAULT_DDD}{digits}")
                if not phone:
                    errors["phone"] = "Telefone inválido. Informe com DDD, ex: (43) 99999-9999"
            except Exception:
                errors["phone"] = "Telefone inválido. Informe com DDD, ex: (43) 99999-9999"

        if errors:
            return render(request, "storefront/checkout.html", {
                "cart": cart,
                "errors": errors,
                "form_data": {"name": name, "phone": phone_raw, "notes": notes},
            })

        session_key = cart["session_key"]

        # Set handle on session so Order inherits it (enables history lookup)
        from shopman.ordering.models import Session as OmniSession

        try:
            omni_session = OmniSession.objects.get(session_key=session_key, state="open")
            omni_session.handle_type = "phone"
            omni_session.handle_ref = phone
            omni_session.save(update_fields=["handle_type", "handle_ref"])
        except OmniSession.DoesNotExist:
            pass

        # Set customer data on session
        from shopman.ordering.services.modify import ModifyService

        fulfillment_type = request.POST.get("fulfillment_type", "pickup")
        delivery_address = request.POST.get("delivery_address", "").strip()
        delivery_date = request.POST.get("delivery_date", "").strip()
        delivery_time_slot = request.POST.get("delivery_time_slot", "").strip()

        # Preorder validation: cutoff time and max date
        if delivery_date:
            from datetime import date as date_type, time as time_type

            today = timezone.now().date()
            try:
                chosen_date = date_type.fromisoformat(delivery_date)
            except ValueError:
                chosen_date = None

            if chosen_date:
                # Max date: today + 7
                max_date = today + timedelta(days=7)
                if chosen_date > max_date:
                    errors["delivery_date"] = f"Data maxima permitida: {max_date.isoformat()}"
                # Cutoff: orders for tomorrow must be placed before 18h today
                if chosen_date == today + timedelta(days=1):
                    cutoff_hour = 18
                    if timezone.now().hour >= cutoff_hour:
                        errors["delivery_date"] = (
                            f"Encomendas para amanha devem ser feitas ate as {cutoff_hour}h."
                        )

            # Minimum quantity validation for preorders
            if chosen_date and chosen_date > today and "delivery_date" not in errors:
                total_qty = sum(item["qty"] for item in cart["items"])
                try:
                    channel_obj = Channel.objects.get(ref=CHANNEL_CODE)
                    min_qty = (channel_obj.config or {}).get("preorder_min_quantity", 1)
                except Channel.DoesNotExist:
                    min_qty = 1
                if total_qty < min_qty:
                    errors["min_quantity"] = f"Encomenda minima: {min_qty} unidades"

            if errors:
                return render(request, "storefront/checkout.html", {
                    "cart": cart,
                    "errors": errors,
                    "form_data": {
                        "name": name, "phone": phone_raw, "notes": notes,
                        "delivery_date": delivery_date,
                        "delivery_time_slot": delivery_time_slot,
                        "fulfillment_type": fulfillment_type,
                    },
                })

        ops = [
            {"op": "set_data", "path": "customer.name", "value": name},
            {"op": "set_data", "path": "customer.phone", "value": phone},
            {"op": "set_data", "path": "fulfillment_type", "value": fulfillment_type},
        ]
        if notes:
            ops.append({"op": "set_data", "path": "customer.notes", "value": notes})
            ops.append({"op": "set_data", "path": "order_notes", "value": notes})
        if fulfillment_type == "delivery" and delivery_address:
            ops.append({"op": "set_data", "path": "delivery_address", "value": delivery_address})
        if delivery_date:
            ops.append({"op": "set_data", "path": "delivery_date", "value": delivery_date})
        if delivery_time_slot:
            ops.append({"op": "set_data", "path": "delivery_time_slot", "value": delivery_time_slot})

        ModifyService.modify_session(
            session_key=session_key,
            channel_ref=CHANNEL_CODE,
            ops=ops,
        )

        # Run stock check before commit (if channel requires it)
        from shopman.ordering.models import Directive as OmniDirective

        try:
            channel_obj = Channel.objects.get(ref=CHANNEL_CODE)
            required_checks = (channel_obj.config or {}).get("required_checks_on_commit", [])

            if "stock" in required_checks:
                # Re-read session after modify (rev was incremented)
                from shopman.ordering.models import Session as OmniSession

                omni_session = OmniSession.objects.get(session_key=session_key, state="open")
                stock_directive = OmniDirective.objects.create(
                    topic="stock.hold",
                    payload={
                        "session_key": session_key,
                        "channel_ref": CHANNEL_CODE,
                        "rev": omni_session.rev,
                        "items": [
                            {"sku": item["sku"], "qty": item["qty"]}
                            for item in omni_session.items
                        ],
                    },
                )
                # Directive auto-dispatches via post_save signal
                stock_directive.refresh_from_db()
                if stock_directive.status == "failed":
                    omni_session.refresh_from_db()
                    issues = omni_session.data.get("issues", [])
                    stock_errors = [i.get("message", "Estoque insuficiente") for i in issues if i.get("blocking")]
                    return render(request, "storefront/checkout.html", {
                        "cart": cart,
                        "errors": {"stock": " | ".join(stock_errors) or "Estoque insuficiente para um ou mais itens."},
                        "form_data": {"name": name, "phone": phone_raw, "notes": notes},
                    })
        except Channel.DoesNotExist:
            pass

        # Commit session → create order
        idempotency_key = generate_idempotency_key()
        result = CommitService.commit(
            session_key=session_key,
            channel_ref=CHANNEL_CODE,
            idempotency_key=idempotency_key,
        )

        # Store fulfillment data on order (also in order.data for handlers)
        order_ref = result["order_ref"]
        try:
            order = Order.objects.get(ref=order_ref)
            order.data["fulfillment_type"] = fulfillment_type
            if fulfillment_type == "delivery" and delivery_address:
                order.data["delivery_address"] = delivery_address
            if delivery_date:
                order.data["delivery_date"] = delivery_date
            if delivery_time_slot:
                order.data["delivery_time_slot"] = delivery_time_slot
            if notes:
                order.data["order_notes"] = notes
            order.save(update_fields=["data", "updated_at"])
        except Order.DoesNotExist:
            pass

        # Clear cart from Django session
        request.session.pop("omniman_session_key", None)

        # If channel has pix.generate in directives, redirect to payment
        try:
            channel = Channel.objects.get(ref=CHANNEL_CODE)
            directives = (channel.config or {}).get("post_commit_directives", [])
            if "pix.generate" in directives:
                return redirect("storefront:order_payment", ref=order_ref)
        except Channel.DoesNotExist:
            pass

        return redirect("storefront:order_tracking", ref=order_ref)


class PaymentView(View):
    """PIX payment page — shows QR code, copy-paste code, and expiry timer."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        payment = order.data.get("payment", {})

        return render(request, "storefront/payment.html", {
            "order": order,
            "payment": payment,
            "total_display": f"R$ {format_money(order.total_q)}",
        })


class PaymentStatusView(View):
    """HTMX partial: polls payment status, redirects when paid."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        payment = order.data.get("payment", {})

        # Check if payment was captured
        is_paid = payment.get("status") == "captured"
        is_cancelled = order.status == "cancelled"

        if is_paid:
            response = HttpResponse("")
            response["HX-Redirect"] = f"/pedido/{order.ref}/"
            return response

        return render(request, "storefront/partials/payment_status.html", {
            "order": order,
            "payment": payment,
            "is_cancelled": is_cancelled,
        })


class MockPaymentConfirmView(View):
    """
    DEV ONLY: Simulate PIX payment confirmation.

    Updates order.data["payment"]["status"] to "captured" and transitions
    the order to "confirmed". In production this would be a webhook from
    the payment gateway.
    """

    def post(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)

        payment = order.data.get("payment", {})
        if payment.get("status") == "captured":
            # Already paid — redirect
            return redirect("storefront:order_tracking", ref=ref)

        # Mark payment as captured
        payment["status"] = "captured"
        payment["captured_at"] = timezone.now().isoformat()
        order.data["payment"] = payment
        order.save(update_fields=["data", "updated_at"])

        # Emit payment event
        order.emit_event(
            event_type="payment.captured",
            actor="mock_payment",
            payload={"method": "pix", "amount_q": payment.get("amount_q", order.total_q)},
        )

        # Transition to confirmed (if still new)
        if order.status == "new":
            order.transition_status("confirmed", actor="payment.pix")

        return redirect("storefront:order_tracking", ref=ref)


class OrderConfirmationView(View):
    """Order confirmation page."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        items = order.items.all()

        # Enrich items with display info
        enriched_items = []
        for item in items:
            enriched_items.append({
                "sku": item.sku,
                "name": item.name or item.sku,
                "qty": item.qty,
                "unit_price_display": f"R$ {format_money(item.unit_price_q)}",
                "total_display": f"R$ {format_money(item.line_total_q)}",
            })

        return render(request, "storefront/order_confirmation.html", {
            "order": order,
            "items": enriched_items,
            "total_display": f"R$ {format_money(order.total_q)}",
        })


# ── Tracking Views ────────────────────────────────────────────────


STATUS_LABELS = {
    "new": "Recebido",
    "confirmed": "Confirmado",
    "processing": "Em Preparo",
    "ready": "Pronto",
    "dispatched": "Despachado",
    "delivered": "Entregue",
    "completed": "Concluído",
    "cancelled": "Cancelado",
    "returned": "Devolvido",
}

STATUS_COLORS = {
    "new": "bg-blue-100 text-blue-800",
    "confirmed": "bg-indigo-100 text-indigo-800",
    "processing": "bg-yellow-100 text-yellow-800",
    "ready": "bg-green-100 text-green-800",
    "dispatched": "bg-purple-100 text-purple-800",
    "delivered": "bg-teal-100 text-teal-800",
    "completed": "bg-green-200 text-green-900",
    "cancelled": "bg-red-100 text-red-800",
    "returned": "bg-gray-100 text-gray-800",
}


def _build_tracking_context(order: Order) -> dict:
    """Build shared context for tracking page and status partial."""
    events = order.events.order_by("seq")
    timeline = []
    for event in events:
        payload = event.payload or {}
        label = STATUS_LABELS.get(payload.get("new_status", ""), event.type)
        timeline.append({
            "label": label,
            "type": event.type,
            "timestamp": event.created_at,
            "payload": payload,
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

    return {
        "order": order,
        "status_label": STATUS_LABELS.get(order.status, order.status),
        "status_color": STATUS_COLORS.get(order.status, "bg-gray-100 text-gray-800"),
        "timeline": timeline,
        "items": items,
        "total_display": f"R$ {format_money(order.total_q)}",
    }


class OrderTrackingView(View):
    """Full order tracking page with HTMX polling for status updates."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        ctx = _build_tracking_context(order)
        return render(request, "storefront/tracking.html", ctx)


class OrderStatusPartialView(View):
    """HTMX partial: returns status badge + timeline for polling."""

    def get(self, request: HttpRequest, ref: str) -> HttpResponse:
        order = get_object_or_404(Order, ref=ref)
        ctx = _build_tracking_context(order)
        return render(request, "storefront/partials/order_status.html", ctx)


# ── Floating Cart Bar ────────────────────────────────────────────


class FloatingCartBarView(View):
    """HTMX partial: floating cart bar shown when cart is non-empty."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/partials/floating_cart_bar.html")


# ── Como Funciona ────────────────────────────────────────────────


class HowItWorksView(View):
    """Static page explaining the ordering process."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/como_funciona.html")


# ── History Views ─────────────────────────────────────────────────


class OrderHistoryView(View):
    """Order history lookup by phone number."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/history.html", {"orders": None})

    def post(self, request: HttpRequest) -> HttpResponse:
        phone_raw = request.POST.get("phone", "").strip()
        errors = {}

        if not phone_raw:
            errors["phone"] = "Telefone é obrigatório."
            return render(request, "storefront/history.html", {
                "orders": None,
                "errors": errors,
                "phone_value": phone_raw,
            })

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            errors["phone"] = "Telefone inválido. Use formato com DDD, ex: (43) 99999-9999"
            return render(request, "storefront/history.html", {
                "orders": None,
                "errors": errors,
                "phone_value": phone_raw,
            })

        orders = Order.objects.filter(
            handle_type="phone",
            handle_ref=phone,
        ).order_by("-created_at")[:50]

        enriched = []
        for order in orders:
            enriched.append({
                "ref": order.ref,
                "created_at": order.created_at,
                "total_display": f"R$ {format_money(order.total_q)}",
                "status": order.status,
                "status_label": STATUS_LABELS.get(order.status, order.status),
                "status_color": STATUS_COLORS.get(order.status, "bg-gray-100 text-gray-800"),
            })

        return render(request, "storefront/history.html", {
            "orders": enriched,
            "phone_value": phone_raw,
        })


# ── Account Views ─────────────────────────────────────────────────


@method_decorator(ensure_csrf_cookie, name="dispatch")
class AccountView(View):
    """Account page: phone lookup → customer info + addresses + orders."""

    def get(self, request: HttpRequest) -> HttpResponse:
        # If phone already verified in session, skip the phone form
        verified_phone = request.session.get("storefront_verified_phone")
        if verified_phone:
            from shopman.attending.services import customer as customer_service

            customer = customer_service.get_by_phone(verified_phone)
            if customer:
                return self._render_account(request, customer, verified_phone)
        return render(request, "storefront/account.html", {"customer": None})

    def _render_account(self, request: HttpRequest, customer, phone: str) -> HttpResponse:
        """Render account page with customer data."""
        addresses = customer.addresses.order_by("-is_default", "label")

        orders = Order.objects.filter(
            handle_type="phone",
            handle_ref=phone,
        ).order_by("-created_at")[:10]

        enriched_orders = []
        for order in orders:
            enriched_orders.append({
                "ref": order.ref,
                "created_at": order.created_at,
                "total_display": f"R$ {format_money(order.total_q)}",
                "status": order.status,
                "status_label": STATUS_LABELS.get(order.status, order.status),
                "status_color": STATUS_COLORS.get(order.status, "bg-gray-100 text-gray-800"),
            })

        preferences = None
        try:
            from shopman.attending.contrib.preferences.models import CustomerPreference

            prefs = CustomerPreference.objects.filter(customer=customer).order_by("category", "key")
            if prefs.exists():
                preferences = prefs
        except Exception:
            pass

        return render(request, "storefront/account.html", {
            "customer": customer,
            "addresses": addresses,
            "orders": enriched_orders,
            "preferences": preferences,
            "phone_value": phone,
            "is_verified": True,
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        phone_raw = request.POST.get("phone", "").strip()
        errors = {}

        if not phone_raw:
            errors["phone"] = "Telefone é obrigatório."
            return render(request, "storefront/account.html", {
                "customer": None,
                "errors": errors,
                "phone_value": phone_raw,
            })

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            errors["phone"] = "Telefone inválido. Use formato com DDD, ex: (43) 99999-9999"
            return render(request, "storefront/account.html", {
                "customer": None,
                "errors": errors,
                "phone_value": phone_raw,
            })

        if not phone:
            # Try with default DDD
            digits = "".join(c for c in phone_raw if c.isdigit())
            if 8 <= len(digits) <= 9:
                try:
                    phone = normalize_phone(f"{DEFAULT_DDD}{digits}")
                except Exception:
                    pass
            if not phone:
                errors["phone"] = "Telefone inválido. Use formato com DDD, ex: (43) 99999-9999"
                return render(request, "storefront/account.html", {
                    "customer": None,
                    "errors": errors,
                    "phone_value": phone_raw,
                })

        from shopman.attending.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)
        if not customer:
            return render(request, "storefront/account.html", {
                "customer": None,
                "not_found": True,
                "phone_value": phone_raw,
            })

        # Build context
        addresses = customer.addresses.order_by("-is_default", "label")

        orders = Order.objects.filter(
            handle_type="phone",
            handle_ref=phone,
        ).order_by("-created_at")[:10]

        enriched_orders = []
        for order in orders:
            enriched_orders.append({
                "ref": order.ref,
                "created_at": order.created_at,
                "total_display": f"R$ {format_money(order.total_q)}",
                "status": order.status,
                "status_label": STATUS_LABELS.get(order.status, order.status),
                "status_color": STATUS_COLORS.get(order.status, "bg-gray-100 text-gray-800"),
            })

        # Preferences (optional)
        preferences = None
        try:
            from shopman.attending.contrib.preferences.models import CustomerPreference

            prefs = CustomerPreference.objects.filter(customer=customer).order_by("category", "key")
            if prefs.exists():
                preferences = prefs
        except Exception:
            pass

        return render(request, "storefront/account.html", {
            "customer": customer,
            "addresses": addresses,
            "orders": enriched_orders,
            "preferences": preferences,
            "phone_value": phone_raw,
        })


# ── Address CRUD Views (HTMX) ────────────────────────────────────


def _get_customer_from_session(request: HttpRequest):
    """Get customer from phone stored in request session."""
    from shopman.attending.services import customer as customer_service

    phone = request.session.get("account_phone")
    if not phone:
        return None
    return customer_service.get_by_phone(phone)


class AddressCreateView(View):
    """HTMX: create new address, return updated address list."""

    def post(self, request: HttpRequest) -> HttpResponse:
        from shopman.attending.models import CustomerAddress

        phone = request.POST.get("customer_phone", "").strip()
        if not phone:
            return HttpResponse("Telefone não informado.", status=400)

        try:
            phone = normalize_phone(phone)
        except Exception:
            return HttpResponse("Telefone inválido.", status=400)

        from shopman.attending.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)
        if not customer:
            return HttpResponse("Cliente não encontrado.", status=404)

        label = request.POST.get("label", "home")
        label_custom = request.POST.get("label_custom", "").strip()
        formatted_address = request.POST.get("formatted_address", "").strip()
        route = request.POST.get("route", "").strip()
        street_number = request.POST.get("street_number", "").strip()
        neighborhood = request.POST.get("neighborhood", "").strip()
        city = request.POST.get("city", "").strip()
        complement = request.POST.get("complement", "").strip()
        delivery_instructions = request.POST.get("delivery_instructions", "").strip()
        is_default = request.POST.get("is_default") == "on"

        if not formatted_address:
            # Build formatted_address from components
            parts = []
            if route:
                parts.append(route)
            if street_number:
                parts.append(street_number)
            if neighborhood:
                parts.append(f"- {neighborhood}")
            if city:
                parts.append(f"- {city}")
            formatted_address = " ".join(parts) if parts else ""

        if not formatted_address:
            return render(request, "storefront/partials/address_form.html", {
                "customer": customer,
                "form_errors": {"formatted_address": "Endereço é obrigatório."},
                "form_data": request.POST,
            })

        addr = CustomerAddress.objects.create(
            customer=customer,
            label=label,
            label_custom=label_custom,
            formatted_address=formatted_address,
            route=route,
            street_number=street_number,
            neighborhood=neighborhood,
            city=city,
            complement=complement,
            delivery_instructions=delivery_instructions,
            is_default=is_default,
        )

        addresses = customer.addresses.order_by("-is_default", "label")
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })


class AddressUpdateView(View):
    """HTMX: update existing address, return updated item."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        from shopman.attending.models import CustomerAddress

        addr = get_object_or_404(CustomerAddress, pk=pk)
        customer = addr.customer

        # Verify phone matches
        phone = request.POST.get("customer_phone", "").strip()
        if phone:
            try:
                phone = normalize_phone(phone)
            except Exception:
                phone = ""
            if phone != customer.phone:
                return HttpResponse("Acesso não autorizado.", status=403)

        addr.label = request.POST.get("label", addr.label)
        addr.label_custom = request.POST.get("label_custom", "").strip()
        addr.formatted_address = request.POST.get("formatted_address", addr.formatted_address).strip()
        addr.route = request.POST.get("route", "").strip()
        addr.street_number = request.POST.get("street_number", "").strip()
        addr.neighborhood = request.POST.get("neighborhood", "").strip()
        addr.city = request.POST.get("city", "").strip()
        addr.complement = request.POST.get("complement", "").strip()
        addr.delivery_instructions = request.POST.get("delivery_instructions", "").strip()

        if not addr.formatted_address:
            parts = []
            if addr.route:
                parts.append(addr.route)
            if addr.street_number:
                parts.append(addr.street_number)
            if addr.neighborhood:
                parts.append(f"- {addr.neighborhood}")
            if addr.city:
                parts.append(f"- {addr.city}")
            addr.formatted_address = " ".join(parts) if parts else ""

        addr.save()

        addresses = customer.addresses.order_by("-is_default", "label")
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })


class AddressDeleteView(View):
    """HTMX: delete address, return updated list."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        from shopman.attending.models import CustomerAddress

        addr = get_object_or_404(CustomerAddress, pk=pk)
        customer = addr.customer

        phone = request.POST.get("customer_phone", "").strip()
        if phone:
            try:
                phone = normalize_phone(phone)
            except Exception:
                phone = ""
            if phone != customer.phone:
                return HttpResponse("Acesso não autorizado.", status=403)

        addr.delete()

        addresses = customer.addresses.order_by("-is_default", "label")
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })


class AddressSetDefaultView(View):
    """HTMX: set address as default, return updated list."""

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        from shopman.attending.models import CustomerAddress

        addr = get_object_or_404(CustomerAddress, pk=pk)
        customer = addr.customer

        phone = request.POST.get("customer_phone", "").strip()
        if phone:
            try:
                phone = normalize_phone(phone)
            except Exception:
                phone = ""
            if phone != customer.phone:
                return HttpResponse("Acesso não autorizado.", status=403)

        addr.is_default = True
        addr.save()  # save() handles unsetting other defaults

        addresses = customer.addresses.order_by("-is_default", "label")
        return render(request, "storefront/partials/address_list.html", {
            "addresses": addresses,
            "customer": customer,
        })


# ── Inline Auth Views (Doorman) ──────────────────────────────────


class RequestCodeView(View):
    """HTMX: request magic code for phone verification during checkout."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if not HAS_DOORMAN:
            return HttpResponse("")

        phone_raw = request.POST.get("phone", "").strip()
        if not phone_raw:
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": "Telefone não informado.",
            })

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": "Telefone inválido.",
            })

        from shopman.gating.services.verification import VerificationService

        ip = request.META.get("REMOTE_ADDR")
        result = VerificationService.request_code(
            target_value=phone,
            purpose="login",
            delivery_method="whatsapp",
            ip_address=ip,
        )

        if not result.success:
            _send_translations = {
                "Too many attempts. Please wait a few minutes.": "Muitas tentativas. Aguarde alguns minutos.",
                "Please wait before requesting a new code.": "Aguarde antes de solicitar um novo código.",
                "Too many attempts from this location.": "Muitas tentativas deste local.",
                "Failed to send code.": "Falha ao enviar código.",
                "Error sending code.": "Erro ao enviar código.",
            }
            raw = result.error or ""
            error_msg = _send_translations.get(raw, raw) or "Erro ao enviar código."
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": error_msg,
                "phone": phone,
                "can_retry": "aguarde" not in error_msg.lower(),
            })

        return render(request, "storefront/partials/auth_verify_code.html", {
            "phone": phone,
        })


class VerifyCodeView(View):
    """HTMX: verify magic code for phone during checkout."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if not HAS_DOORMAN:
            return HttpResponse("")

        phone_raw = request.POST.get("phone", "").strip()
        code_input = request.POST.get("code", "").strip()

        if not phone_raw or not code_input:
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": "Código não informado.",
                "phone": phone_raw,
            })

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": "Telefone inválido.",
            })

        from shopman.gating.services.verification import VerificationService

        result = VerificationService.verify_for_login(
            target_value=phone,
            code_input=code_input,
            request=request,
        )

        if not result.success:
            # Translate Doorman error messages to PT-BR
            _error_translations = {
                "Incorrect code.": "Código incorreto.",
                "Code expired. Please request a new one.": "Código expirado. Solicite um novo.",
                "Account not found. Please contact support.": "Conta não encontrada.",
            }
            raw_error = result.error or ""
            error_msg = _error_translations.get(raw_error, raw_error) or "Código inválido."
            if result.attempts_remaining is not None and result.attempts_remaining > 0:
                error_msg += f" ({result.attempts_remaining} tentativa(s) restante(s))"
            return render(request, "storefront/partials/auth_verify_code.html", {
                "phone": phone,
                "error_message": error_msg,
            })

        # Mark session as verified
        request.session["storefront_verified_phone"] = phone
        if result.customer:
            request.session["storefront_verified_name"] = result.customer.name or ""

        return render(request, "storefront/partials/auth_confirmed.html", {
            "phone": phone,
        })


# ── Sitemap View ──────────────────────────────────────────────────


class SitemapView(View):
    """Generate a simple XML sitemap with menu, collections, and product URLs."""

    def get(self, request: HttpRequest) -> HttpResponse:
        from django.urls import reverse

        urls = []
        base = request.build_absolute_uri("/").rstrip("/")

        # Menu
        urls.append({"loc": base + reverse("storefront:menu"), "priority": "1.0", "changefreq": "daily"})
        urls.append({"loc": base + reverse("storefront:como_funciona"), "priority": "0.5", "changefreq": "monthly"})

        # Collections
        for col in Collection.objects.filter(is_active=True):
            urls.append({
                "loc": base + reverse("storefront:menu_collection", args=[col.slug]),
                "priority": "0.8",
                "changefreq": "daily",
            })

        # Products
        for product in Product.objects.filter(is_published=True):
            urls.append({
                "loc": base + reverse("storefront:product_detail", args=[product.sku]),
                "priority": "0.7",
                "changefreq": "daily",
            })

        return render(request, "storefront/sitemap.xml", {"urls": urls}, content_type="application/xml")
