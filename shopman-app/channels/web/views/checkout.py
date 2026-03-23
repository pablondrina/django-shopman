from __future__ import annotations

from datetime import timedelta

from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from shopman.utils.monetary import format_money
from shopman.utils.phone import normalize_phone
from shopman.ordering.ids import generate_idempotency_key
from shopman.ordering.models import Channel, Order
from shopman.ordering.services.commit import CommitService

from ..cart import CHANNEL_CODE, CartService
from ..constants import DEFAULT_DDD, STOREFRONT_CHANNEL_REF


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
            from datetime import date as date_type

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
