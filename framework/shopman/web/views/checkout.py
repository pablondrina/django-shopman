"""Refactored CheckoutView — uses services.checkout.process() for commit."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie
from django_ratelimit.decorators import ratelimit

logger = logging.getLogger(__name__)

from shopman.ordering.ids import generate_idempotency_key
from shopman.ordering.models import Channel
from shopman.services.checkout_defaults import CheckoutDefaultsService
from shopman.utils.phone import normalize_phone

from ..cart import CHANNEL_REF, CartService
from ..constants import get_default_ddd
from ._helpers import _get_availability, _min_order_progress
from .tracking import CepLookupView, OrderConfirmationView  # noqa: F401


@method_decorator(ensure_csrf_cookie, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="3/m", method="POST", block=False), name="post")
class CheckoutView(View):
    """Checkout: review order and submit.

    Refactored to use shopman.services.checkout.process() for the commit step.
    """

    def _checkout_page_context(self, request: HttpRequest, cart: dict) -> dict:
        """Contexto comum GET e re-render com erros (WP-S3: paridade total)."""
        ctx: dict = {
            "cart": cart,
            "checkout_defaults": {},
            "saved_addresses": [],
            "payment_methods": self._get_payment_methods(),
            "cutoff_info": self._get_cutoff_info(),
            "minimum_order_warning": _min_order_progress(cart["subtotal_q"]),
        }
        customer_info = getattr(request, "customer", None)
        ctx["customer_info"] = customer_info
        ctx["is_verified"] = customer_info is not None
        if customer_info is None:
            return ctx

        from shopman.customers.services import customer as customer_service

        customer_obj = customer_service.get_by_uuid(customer_info.uuid)
        if customer_obj:
            addresses = list(
                customer_obj.addresses.order_by("-is_default", "label").values(
                    "id",
                    "formatted_address",
                    "complement",
                    "delivery_instructions",
                    "is_default",
                )
            )
            for addr in addresses:
                addr["label"] = customer_obj.addresses.get(
                    id=addr["id"]
                ).display_label
            ctx["saved_addresses"] = addresses

            try:
                checkout_defaults = CheckoutDefaultsService.get_defaults(
                    customer_ref=customer_obj.ref,
                    channel_ref=CHANNEL_REF,
                )
                if checkout_defaults:
                    ctx["checkout_defaults"] = checkout_defaults
            except Exception as e:
                logger.warning("checkout_defaults_failed: %s", e, exc_info=True)

            # Loyalty balance for points redemption
            try:
                from shopman.customers.contrib.loyalty.service import LoyaltyService
                from shopman.utils.monetary import format_money

                balance = LoyaltyService.get_balance(customer_obj.ref)
                ctx["loyalty_balance"] = balance
                ctx["loyalty_value_display"] = f"R$ {format_money(balance)}" if balance > 0 else None
            except Exception as e:
                logger.warning("loyalty_balance_failed: %s", e, exc_info=True)
                ctx["loyalty_balance"] = 0
                ctx["loyalty_value_display"] = None

        return ctx

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        if not cart["items"]:
            return redirect("storefront:cart")

        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return redirect("/login/?next=/checkout/")

        ctx = self._checkout_page_context(request, cart)
        ctx["form_data"] = {
            "phone": customer_info.phone or "",
            "name": customer_info.name or "",
        }
        return render(request, "storefront/checkout.html", ctx)

    def post(self, request: HttpRequest) -> HttpResponse:
        if getattr(request, "limited", False):
            return render(request, "storefront/partials/rate_limited.html", status=429)

        cart = CartService.get_cart(request)
        if not cart["items"]:
            return redirect("storefront:cart")

        name = request.POST.get("name", "").strip()
        phone_raw = request.POST.get("phone", "").strip()
        notes = request.POST.get("notes", "").strip()

        # ── Phone validation ──
        phone = ""
        errors = {}
        if not phone_raw:
            errors["phone"] = "Telefone é obrigatório."
        else:
            try:
                phone = normalize_phone(phone_raw)
                if not phone:
                    digits = "".join(c for c in phone_raw if c.isdigit())
                    if 8 <= len(digits) <= 9:
                        phone = normalize_phone(f"{get_default_ddd()}{digits}")
                if not phone:
                    errors["phone"] = (
                        "Telefone inválido. Informe com DDD, ex: (43) 99999-9999"
                    )
            except Exception as e:
                logger.warning("phone_normalization_failed: %s", e, exc_info=True)
                errors["phone"] = (
                    "Telefone inválido. Informe com DDD, ex: (43) 99999-9999"
                )

        # Name required only for new customers
        if not errors and not name:
            from shopman.customers.services import customer as cs_check

            existing = cs_check.get_by_phone(phone) if phone else None
            if not existing or not existing.first_name:
                errors["name"] = "Nome é obrigatório."

        if errors:
            return self._render_with_errors(
                request, cart, errors, name, phone_raw, notes
            )

        # Resolve name from existing customer if not provided
        if not name:
            from shopman.customers.services import customer as cs_name

            existing = cs_name.get_by_phone(phone)
            if existing and existing.first_name:
                name = existing.name

        session_key = cart["session_key"]

        # Set handle on session for history lookup
        from shopman.ordering.models import Session as OmniSession

        try:
            omni_session = OmniSession.objects.get(
                session_key=session_key, state="open"
            )
            omni_session.handle_type = "phone"
            omni_session.handle_ref = phone
            omni_session.save(update_fields=["handle_type", "handle_ref"])
        except OmniSession.DoesNotExist:
            pass

        # ── Parse form fields ──
        fulfillment_type = request.POST.get("fulfillment_type", "pickup")
        delivery_address = request.POST.get("delivery_address", "").strip()
        delivery_date = request.POST.get("delivery_date", "").strip()
        delivery_time_slot = request.POST.get("delivery_time_slot", "").strip()

        # Structured address from checkout_address component
        addr_data = self._parse_address_data(request)

        # Resolve saved address if selected
        saved_address_id = request.POST.get("saved_address_id", "").strip()
        if saved_address_id and fulfillment_type == "delivery" and not delivery_address:
            from shopman.customers.models import CustomerAddress

            try:
                addr = CustomerAddress.objects.get(id=int(saved_address_id))
                parts = [addr.formatted_address]
                if addr.complement:
                    parts.append(f"- {addr.complement}")
                delivery_address = " ".join(parts)
            except (CustomerAddress.DoesNotExist, ValueError):
                pass

        chosen_method = self._resolve_payment_method(request)

        minimum_order_warning = _min_order_progress(cart["subtotal_q"])
        if minimum_order_warning:
            errors["minimum_order"] = (
                "Faltam "
                f"{minimum_order_warning['remaining_display']} para atingir o pedido mínimo de "
                f"{minimum_order_warning['minimum_display']}."
            )

        address_errors = self._validate_checkout_form(
            fulfillment_type=fulfillment_type,
            delivery_address=delivery_address,
            addr_data=addr_data,
            payment_method=chosen_method,
        )
        if address_errors:
            errors.update(address_errors)

        # Estoque: sempre no servidor (WP-S3 — não depender só do flag `stock_checked` do cliente)
        stock_errors, stock_check_unavailable = self._check_cart_stock(request, cart)
        if stock_errors:
            errors["stock"] = stock_errors[0]["message"]

        if errors:
            return self._render_with_errors(
                request,
                cart,
                errors,
                name,
                phone_raw,
                notes,
                extra_form_data={
                    "delivery_date": delivery_date,
                    "delivery_time_slot": delivery_time_slot,
                    "fulfillment_type": fulfillment_type,
                    "delivery_address": delivery_address,
                    "saved_address_id": saved_address_id,
                    "payment_method": chosen_method,
                    "addr_route": addr_data.get("route", ""),
                    "addr_street_number": addr_data.get("street_number", ""),
                    "addr_complement": addr_data.get("complement", ""),
                    "addr_neighborhood": addr_data.get("neighborhood", ""),
                    "addr_city": addr_data.get("city", ""),
                    "addr_state_code": addr_data.get("state_code", ""),
                    "addr_postal_code": addr_data.get("postal_code", ""),
                    "addr_delivery_instructions": addr_data.get(
                        "delivery_instructions", ""
                    ),
                },
            )

        # ── Preorder validation ──
        if delivery_date:
            preorder_errors = self._validate_preorder(delivery_date, cart)
            if preorder_errors:
                return self._render_with_errors(
                    request,
                    cart,
                    preorder_errors,
                    name,
                    phone_raw,
                    notes,
                    extra_form_data={
                        "delivery_date": delivery_date,
                        "delivery_time_slot": delivery_time_slot,
                        "fulfillment_type": fulfillment_type,
                    },
                )

        # ── Build checkout data and commit via service ──
        from shopman.services.checkout import process as checkout_process

        checkout_data = {
            "customer": {"name": name, "phone": phone},
            "fulfillment_type": fulfillment_type,
        }
        if stock_check_unavailable:
            checkout_data["stock_check_unavailable"] = True
        if notes:
            checkout_data["order_notes"] = notes
        if fulfillment_type == "delivery" and delivery_address:
            checkout_data["delivery_address"] = delivery_address
            if addr_data.get("formatted_address"):
                checkout_data["delivery_address_structured"] = {
                    k: v for k, v in addr_data.items() if v
                }
        if delivery_date:
            checkout_data["delivery_date"] = delivery_date
        if delivery_time_slot:
            checkout_data["delivery_time_slot"] = delivery_time_slot
        if chosen_method in ("pix", "card"):
            checkout_data["payment"] = {"method": chosen_method}

        # Loyalty redemption
        use_loyalty = request.POST.get("use_loyalty") == "true"
        if use_loyalty:
            customer_info = getattr(request, "customer", None)
            if customer_info:
                try:
                    from shopman.customers.contrib.loyalty.service import LoyaltyService
                    from shopman.ordering.models import Session as OrderingSession
                    balance = LoyaltyService.get_balance_by_uuid(customer_info.uuid) if hasattr(LoyaltyService, "get_balance_by_uuid") else 0
                    if balance <= 0:
                        # Fallback: get customer ref and use get_balance
                        from shopman.customers.services import customer as customer_service
                        customer_obj = customer_service.get_by_uuid(customer_info.uuid)
                        if customer_obj:
                            balance = LoyaltyService.get_balance(customer_obj.ref)
                    if balance > 0:
                        checkout_data["loyalty"] = {"redeem_points_q": balance}
                except Exception as e:
                    logger.warning("loyalty_redeem_failed: %s", e, exc_info=True)

        idempotency_key = generate_idempotency_key()
        try:
            result = checkout_process(
                session_key=session_key,
                channel_ref=CHANNEL_REF,
                data=checkout_data,
                idempotency_key=idempotency_key,
            )
        except Exception as exc:
            # Map ordering ValidationError to user-visible checkout error
            from shopman.ordering.exceptions import ValidationError as OrderingValidationError

            if isinstance(exc, OrderingValidationError):
                field = "delivery_address" if exc.code == "delivery_zone_not_covered" else "checkout"
                errors[field] = exc.message
                return self._render_with_errors(
                    request, cart, errors, name, phone_raw, notes,
                    extra_form_data={
                        "delivery_date": delivery_date,
                        "delivery_time_slot": delivery_time_slot,
                        "fulfillment_type": fulfillment_type,
                        "delivery_address": delivery_address,
                        "saved_address_id": saved_address_id,
                        "payment_method": chosen_method,
                        "addr_route": addr_data.get("route", ""),
                        "addr_street_number": addr_data.get("street_number", ""),
                        "addr_complement": addr_data.get("complement", ""),
                        "addr_neighborhood": addr_data.get("neighborhood", ""),
                        "addr_city": addr_data.get("city", ""),
                        "addr_state_code": addr_data.get("state_code", ""),
                        "addr_postal_code": addr_data.get("postal_code", ""),
                        "addr_delivery_instructions": addr_data.get("delivery_instructions", ""),
                    },
                )
            raise
        order_ref = result["order_ref"]

        # ── Ensure customer exists ──
        from django.db import IntegrityError

        from shopman.customers.services import customer as customer_service

        customer_obj = customer_service.get_by_phone(phone)
        if customer_obj:
            if name and not customer_obj.first_name:
                customer_obj.first_name = name
                customer_obj.save(update_fields=["first_name"])
        else:
            import uuid as uuid_lib

            try:
                customer_obj = customer_service.create(
                    ref=f"WEB-{str(uuid_lib.uuid4())[:8].upper()}",
                    first_name=name,
                    phone=phone,
                )
            except IntegrityError:
                customer_obj = customer_service.get_by_phone(phone)

        # ── Save checkout defaults ──
        if request.POST.get("save_as_default") and customer_obj:
            try:
                defaults_data = {
                    "fulfillment_type": fulfillment_type,
                    "payment_method": chosen_method,
                }
                if fulfillment_type == "delivery":
                    if saved_address_id:
                        defaults_data["delivery_address_id"] = int(saved_address_id)
                    if delivery_time_slot:
                        defaults_data["delivery_time_slot"] = delivery_time_slot
                if notes:
                    defaults_data["order_notes"] = notes
                CheckoutDefaultsService.save_defaults(
                    customer_ref=customer_obj.ref,
                    channel_ref=CHANNEL_REF,
                    data=defaults_data,
                    source=f"order:{order_ref}",
                )
            except Exception as e:
                logger.warning("save_checkout_defaults_failed order=%s: %s", order_ref, e, exc_info=True)

        # Clear cart
        request.session.pop("cart_session_key", None)

        # Redirect to payment or tracking
        if chosen_method in ("pix", "card"):
            # If payment initiation failed (gateway down), redirect to tracking with a message
            try:
                from shopman.ordering.models import Order as _Order
                _order = _Order.objects.get(ref=order_ref)
                _payment_status = (_order.data or {}).get("payment", {}).get("status")
                if _payment_status == "pending_retry":
                    from django.contrib import messages
                    messages.warning(request, "Pagamento será processado em breve. Acompanhe seu pedido.")
                    return redirect("storefront:order_tracking", ref=order_ref)
            except Exception:
                pass
            return redirect("storefront:order_payment", ref=order_ref)
        return redirect("storefront:order_tracking", ref=order_ref)

    # ── Helpers ──

    @staticmethod
    def _get_payment_methods() -> list[str]:
        try:
            channel = Channel.objects.get(ref=CHANNEL_REF)
            config = channel.config or {}
            payment = config.get("payment", {})
            method = (
                payment.get("method", "counter")
                if isinstance(payment, dict)
                else payment
            )
            if isinstance(method, list):
                return method
            return [method]
        except Channel.DoesNotExist:
            return ["counter"]

    def _resolve_payment_method(self, request: HttpRequest) -> str:
        payment_methods = self._get_payment_methods()
        if len(payment_methods) > 1:
            chosen_method = request.POST.get("payment_method", payment_methods[0])
            if chosen_method not in payment_methods:
                chosen_method = payment_methods[0]
            return chosen_method
        return payment_methods[0] if payment_methods else "counter"

    @staticmethod
    def _get_cutoff_info() -> dict | None:
        try:
            channel = Channel.objects.get(ref=CHANNEL_REF)
            cutoff_hour = (channel.config or {}).get("cutoff_hour", 18)
        except Channel.DoesNotExist:
            cutoff_hour = 18

        now = timezone.localtime()
        past_cutoff = now.hour >= cutoff_hour

        if past_cutoff:
            next_date = (now + timedelta(days=2)).strftime("%d/%m")
            return {
                "past_cutoff": True,
                "cutoff_hour": cutoff_hour,
                "message": f"Pedidos para amanhã encerrados. Próxima entrega: {next_date}",
            }
        return {
            "past_cutoff": False,
            "cutoff_hour": cutoff_hour,
            "message": f"Pedidos até {cutoff_hour}h para entrega amanhã",
        }

    @staticmethod
    def _parse_address_data(request: HttpRequest) -> dict:
        addr_data = {
            "route": request.POST.get("addr_route", "").strip(),
            "street_number": request.POST.get("addr_street_number", "").strip(),
            "complement": request.POST.get("addr_complement", "").strip(),
            "neighborhood": request.POST.get("addr_neighborhood", "").strip(),
            "city": request.POST.get("addr_city", "").strip(),
            "state_code": request.POST.get("addr_state_code", "").strip(),
            "postal_code": request.POST.get("addr_postal_code", "").strip(),
            "place_id": request.POST.get("addr_place_id", "").strip(),
            "formatted_address": request.POST.get("addr_formatted_address", "").strip(),
            "delivery_instructions": request.POST.get(
                "addr_delivery_instructions", ""
            ).strip(),
            "is_verified": request.POST.get("addr_is_verified", "") == "true",
        }
        try:
            addr_data["latitude"] = float(request.POST.get("addr_latitude", ""))
        except (ValueError, TypeError):
            addr_data["latitude"] = None
        try:
            addr_data["longitude"] = float(request.POST.get("addr_longitude", ""))
        except (ValueError, TypeError):
            addr_data["longitude"] = None
        return addr_data

    @staticmethod
    def _validate_preorder(delivery_date: str, cart: dict) -> dict:
        from datetime import date as date_type

        errors = {}
        today = timezone.now().date()
        try:
            chosen_date = date_type.fromisoformat(delivery_date)
        except ValueError:
            return errors

        max_date = today + timedelta(days=7)
        if chosen_date > max_date:
            errors["delivery_date"] = f"Data maxima permitida: {max_date.isoformat()}"
        if chosen_date == today + timedelta(days=1):
            cutoff_hour = 18
            if timezone.now().hour >= cutoff_hour:
                errors["delivery_date"] = (
                    f"Encomendas para amanha devem ser feitas ate as {cutoff_hour}h."
                )

        if chosen_date > today and "delivery_date" not in errors:
            total_qty = sum(item["qty"] for item in cart["items"])
            try:
                channel_obj = Channel.objects.get(ref=CHANNEL_REF)
                min_qty = (channel_obj.config or {}).get("preorder_min_quantity", 1)
            except Channel.DoesNotExist:
                min_qty = 1
            if total_qty < min_qty:
                errors["min_quantity"] = f"Encomenda minima: {min_qty} unidades"

        return errors

    def _validate_checkout_form(
        self,
        *,
        fulfillment_type: str,
        delivery_address: str,
        addr_data: dict,
        payment_method: str,
    ) -> dict:
        errors = {}
        if fulfillment_type == "delivery":
            has_route = bool((addr_data.get("route") or "").strip())
            has_number = bool((addr_data.get("street_number") or "").strip())
            has_saved_flat_address = bool(delivery_address)
            if not has_saved_flat_address and not has_route:
                errors["delivery_address"] = "Informe o endereço de entrega."
            if has_route and not has_number:
                errors["addr_street_number"] = "Informe o número do endereço."
        if not payment_method:
            errors["payment_method"] = "Selecione uma forma de pagamento."
        return errors

    def _check_cart_stock(self, request: HttpRequest, cart: dict) -> tuple[list[dict], bool]:
        """Check cart items against live stock. Returns (warnings, service_unavailable).

        service_unavailable=True means ALL availability checks failed (stock service down).
        In that case warnings is empty and checkout is allowed to proceed (graceful degradation).
        """
        from decimal import Decimal

        items = cart.get("items", [])
        if not items:
            return [], False

        session_held = self._get_session_held_qty(request)
        warnings = []
        checked = 0
        skipped = 0
        for item in items:
            sku = item.get("sku", "")
            qty = int(Decimal(str(item.get("qty", 0))))
            avail = _get_availability(sku)
            if avail is None:
                skipped += 1
                continue
            checked += 1
            breakdown = avail.get("breakdown", {})
            ready = breakdown.get("ready", Decimal("0"))
            in_prod = breakdown.get("in_production", Decimal("0"))
            d1 = breakdown.get("d1", Decimal("0"))
            available_qty = int(ready + in_prod + d1) + session_held.get(sku, 0)
            if qty > available_qty:
                name = item.get("name") or sku
                if available_qty > 0:
                    message = (
                        f"{name}: disponível {available_qty} unidade(s) no momento."
                    )
                else:
                    message = f"{name} está esgotado no momento."
                warnings.append(
                    {
                        "line_id": item.get("line_id", ""),
                        "sku": sku,
                        "requested_qty": qty,
                        "available_qty": available_qty,
                        "message": message,
                    }
                )

        service_unavailable = skipped > 0 and checked == 0
        if service_unavailable:
            logger.warning(
                "checkout.stock_check_unavailable: %d item(s) skipped, service may be down",
                skipped,
            )
        return warnings, service_unavailable

    @staticmethod
    def _get_session_held_qty(request: HttpRequest) -> dict[str, int]:
        session_key = request.session.get("cart_session_key")
        if not session_key:
            return {}
        try:
            from shopman.stocking.models import Hold

            holds = Hold.objects.filter(metadata__reference=session_key).active()
            held: dict[str, int] = {}
            for hold in holds:
                held[hold.sku] = held.get(hold.sku, 0) + int(hold.quantity)
            return held
        except (ImportError, Exception):
            return {}

    def _render_with_errors(
        self,
        request,
        cart,
        errors,
        name,
        phone_raw,
        notes,
        extra_form_data=None,
    ):
        form_data = {"name": name, "phone": phone_raw, "notes": notes}
        if extra_form_data:
            form_data.update(extra_form_data)
        ctx = self._checkout_page_context(request, cart)
        ctx["errors"] = errors
        ctx["form_data"] = form_data
        return render(request, "storefront/checkout.html", ctx)


class CheckoutOrderSummaryView(View):
    """HTMX: coluna resumo + totais (atualiza após cupom no checkout)."""

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        if not cart.get("items"):
            return HttpResponse("")
        return render(
            request,
            "storefront/partials/checkout_order_summary.html",
            {
                "cart": cart,
                "minimum_order_warning": _min_order_progress(cart["subtotal_q"]),
            },
        )
