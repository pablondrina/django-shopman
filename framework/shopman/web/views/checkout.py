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

from shopman.guestman.contrib.loyalty import LoyaltyService
from shopman.orderman.ids import generate_idempotency_key
from shopman.models import Channel
from shopman.services.checkout_defaults import CheckoutDefaultsService
from shopman.services.order_helpers import parse_commitment_date
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
        import json as _json
        from shopman.models import Shop
        shop = Shop.load()
        shop_defaults = (shop.defaults or {}) if shop else {}
        max_preorder_days = int(shop_defaults.get("max_preorder_days", 30))
        closed_dates = shop_defaults.get("closed_dates", [])

        ctx: dict = {
            "cart": cart,
            "checkout_defaults": {},
            "saved_addresses": [],
            "payment_methods": self._get_payment_methods(),
            "minimum_order_warning": _min_order_progress(cart["subtotal_q"]),
            "max_preorder_days": max_preorder_days,
            "closed_dates_json": _json.dumps(closed_dates),
        }

        # Pickup slots — dynamic from Shop.defaults + production history
        try:
            from shopman.services.pickup_slots import annotate_slots_for_checkout

            cart_skus = [item["sku"] for item in cart.get("items", []) if item.get("sku")]
            ctx.update(annotate_slots_for_checkout(cart_skus))
        except Exception as e:
            logger.warning("pickup_slots_failed: %s", e, exc_info=True)
        customer_info = getattr(request, "customer", None)
        ctx["customer_info"] = customer_info
        ctx["is_verified"] = customer_info is not None
        if customer_info is None:
            return ctx

        from shopman.guestman.services import address as address_service
        from shopman.guestman.services import customer as customer_service

        customer_obj = customer_service.get_by_uuid(customer_info.uuid)
        if customer_obj:
            addresses = [
                {
                    "id": addr.id,
                    "formatted_address": addr.formatted_address,
                    "complement": addr.complement,
                    "delivery_instructions": addr.delivery_instructions,
                    "is_default": addr.is_default,
                    "label": addr.display_label,
                }
                for addr in address_service.addresses(customer_obj.ref)
            ]
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

        pre_cart_key = request.session.get("cart_session_key")
        cart = CartService.get_cart(request)
        if not cart["items"]:
            # Detect expired session: key existed but session is gone
            if pre_cart_key and not request.session.get("cart_session_key"):
                from django.contrib import messages
                messages.warning(request, "Seu carrinho expirou. Adicione os itens novamente.")
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
            except (ValueError, TypeError) as e:
                logger.warning("phone_normalization_failed: %s", e, exc_info=True)
                errors["phone"] = (
                    "Telefone inválido. Informe com DDD, ex: (43) 99999-9999"
                )

        # Name required only for new customers
        if not errors and not name:
            from shopman.guestman.services import customer as cs_check

            existing = cs_check.get_by_phone(phone) if phone else None
            if not existing or not existing.first_name:
                errors["name"] = "Nome é obrigatório."

        if errors:
            return self._render_with_errors(
                request, cart, errors, name, phone_raw, notes
            )

        # Resolve name from existing customer if not provided
        if not name:
            from shopman.guestman.services import customer as cs_name

            existing = cs_name.get_by_phone(phone)
            if existing and existing.first_name:
                name = existing.name

        session_key = cart["session_key"]

        # Set handle on session for history lookup
        from shopman.orderman.models import Session as OmniSession

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
            customer_info = getattr(request, "customer", None)
            from shopman.guestman.services import address as address_service
            from shopman.guestman.services import customer as customer_service

            try:
                if customer_info is not None:
                    customer_obj = customer_service.get_by_uuid(customer_info.uuid)
                    if customer_obj:
                        addr = address_service.get_address(customer_obj.ref, int(saved_address_id))
                        if addr:
                            parts = [addr.formatted_address]
                            if addr.complement:
                                parts.append(f"- {addr.complement}")
                            delivery_address = " ".join(parts)
            except ValueError:
                pass

        chosen_method = self._resolve_payment_method(request)

        # Task 4: Payment method unavailable (e.g. channel removed "pix" after cart was filled)
        if not self._payment_method_available(chosen_method):
            errors["payment_method"] = "Método de pagamento indisponível. Selecione outro."

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

        # Task 3: Repricing warning (non-blocking — inform user, don't block checkout)
        repricing_warnings = self._check_repricing(cart)

        # Estoque: sempre no servidor (WP-S3 — não depender só do flag `stock_checked` do cliente)
        commitment_date = parse_commitment_date(delivery_date)
        stock_errors, stock_check_unavailable = self._check_cart_stock(
            request,
            cart,
            target_date=commitment_date,
        )
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
                repricing_warnings=repricing_warnings,
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

        # ── Slot validation ──
        slot_errors = self._validate_slot(delivery_time_slot, fulfillment_type, delivery_date)
        if slot_errors:
            return self._render_with_errors(
                request,
                cart,
                slot_errors,
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
                    balance = LoyaltyService.get_balance_by_uuid(customer_info.uuid) if hasattr(LoyaltyService, "get_balance_by_uuid") else 0
                    if balance <= 0:
                        # Fallback: get customer ref and use get_balance
                        from shopman.guestman.services import customer as customer_service
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
            # Map orderman ValidationError to user-visible checkout error
            from shopman.orderman.exceptions import ValidationError as OrderingValidationError

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

        from shopman.guestman.services import customer as customer_service

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
            # If payment initiation failed (gateway down), redirect to tracking
            try:
                from shopman.orderman.models import Order as _Order
                _order = _Order.objects.get(ref=order_ref)
                _payment_data = (_order.data or {}).get("payment", {})
                if _payment_data.get("error"):
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
        from shopman.config import ChannelConfig
        try:
            channel = Channel.objects.get(ref=CHANNEL_REF)
        except Channel.DoesNotExist:
            return ["cash"]
        return ChannelConfig.for_channel(channel).payment.available_methods

    def _resolve_payment_method(self, request: HttpRequest) -> str:
        payment_methods = self._get_payment_methods()
        if len(payment_methods) > 1:
            chosen_method = request.POST.get("payment_method", payment_methods[0])
            if chosen_method not in payment_methods:
                chosen_method = payment_methods[0]
            return chosen_method
        return payment_methods[0] if payment_methods else "cash"

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
    def _is_closed_date(date_obj, closed_dates: list) -> tuple[bool, str | None]:
        """Check if date_obj falls within any entry in closed_dates.

        Supports single-date {"date": "YYYY-MM-DD", "label": "..."} and
        range {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "label": "..."}.
        Returns (is_closed, label_or_None).
        """
        from datetime import date as date_type

        for entry in closed_dates:
            label = entry.get("label", "")
            if "date" in entry:
                try:
                    if date_obj == date_type.fromisoformat(entry["date"]):
                        return True, label
                except ValueError:
                    pass
            elif "from" in entry and "to" in entry:
                try:
                    start = date_type.fromisoformat(entry["from"])
                    end = date_type.fromisoformat(entry["to"])
                    if start <= date_obj <= end:
                        return True, label
                except ValueError:
                    pass
        return False, None

    @staticmethod
    def _validate_preorder(delivery_date: str, cart: dict) -> dict:
        from datetime import date as date_type

        errors = {}
        today = timezone.now().date()
        try:
            chosen_date = date_type.fromisoformat(delivery_date)
        except ValueError:
            return errors

        if chosen_date < today:
            errors["delivery_date"] = "Não é possível encomendar para uma data passada."
            return errors

        try:
            from shopman.models import Shop
            shop = Shop.load()
            max_preorder_days = int((shop.defaults or {}).get("max_preorder_days", 30)) if shop else 30
            closed_dates = ((shop.defaults or {}).get("closed_dates", [])) if shop else []
        except Exception:
            max_preorder_days = 30
            closed_dates = []

        max_date = today + timedelta(days=max_preorder_days)
        if chosen_date > max_date:
            errors["delivery_date"] = f"Data máxima permitida: {max_date.strftime('%d/%m/%Y')}"
            return errors

        is_closed, closed_label = CheckoutView._is_closed_date(chosen_date, closed_dates)
        if is_closed:
            suffix = f": {closed_label}" if closed_label else ""
            errors["delivery_date"] = f"Fechado{suffix} — escolha outra data."

        return errors

    @staticmethod
    def _validate_slot(
        delivery_time_slot: str,
        fulfillment_type: str,
        delivery_date: str,
    ) -> dict:
        from datetime import date as date_type, time as time_type

        from shopman.services.pickup_slots import _find_slot_by_ref, get_slots

        errors = {}

        if fulfillment_type == "pickup" and not delivery_time_slot:
            errors["delivery_time_slot"] = "Selecione um horário de retirada."
            return errors

        if not delivery_time_slot:
            return errors

        slots = get_slots()
        slot = _find_slot_by_ref(slots, delivery_time_slot)
        if slot is None:
            errors["delivery_time_slot"] = "Horário de retirada inválido."
            return errors

        # If delivery is for today: slot must be in the future
        today = timezone.now().date()
        is_today = True
        if delivery_date:
            try:
                chosen_date = date_type.fromisoformat(delivery_date)
                is_today = chosen_date == today
            except ValueError:
                is_today = True

        if is_today:
            now_local = timezone.localtime()
            try:
                parts = slot["starts_at"].split(":")
                slot_time = time_type(int(parts[0]), int(parts[1]))
                current_time = now_local.time().replace(second=0, microsecond=0)
                if slot_time <= current_time:
                    errors["delivery_time_slot"] = "Este horário já passou. Selecione um horário futuro."
            except (ValueError, KeyError):
                pass

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

    def _payment_method_available(self, method: str) -> bool:
        """Return True if method is currently offered by the channel."""
        return method in self._get_payment_methods()

    def _check_repricing(self, cart: dict) -> list[dict]:
        """Compare cart item prices against current catalog prices.

        Returns a list of non-blocking warnings for items repriced >5% since
        they were added to cart. The checkout is allowed to proceed regardless.
        """
        items = cart.get("items", [])
        if not items:
            return []

        from shopman.offerman.models import Product

        skus = [item.get("sku", "") for item in items if item.get("sku")]
        if not skus:
            return []

        products_by_sku = {p.sku: p for p in Product.objects.filter(sku__in=skus).only("sku", "name", "base_price_q")}
        warnings = []
        for item in items:
            sku = item.get("sku", "")
            product = products_by_sku.get(sku)
            if not product:
                continue
            cart_price = int(item.get("unit_price_q", 0))
            current_price = int(product.base_price_q)
            if cart_price <= 0 or current_price <= 0:
                continue
            # Calculate divergence relative to current (catalog) price
            divergence = abs(current_price - cart_price) / current_price
            if divergence > 0.05:
                from shopman.utils.monetary import format_money
                warnings.append({
                    "sku": sku,
                    "name": product.name or sku,
                    "cart_price_display": f"R$ {format_money(cart_price)}",
                    "current_price_display": f"R$ {format_money(current_price)}",
                    "message": (
                        f"O preço de {product.name or sku} mudou para "
                        f"R$ {format_money(current_price)}. Deseja continuar?"
                    ),
                })
        return warnings

    def _check_cart_stock(
        self,
        request: HttpRequest,
        cart: dict,
        *,
        target_date=None,
    ) -> tuple[list[dict], bool]:
        """Check cart items against live stock. Returns (warnings, service_unavailable).

        service_unavailable=True means ALL availability checks failed (stock service down).
        In that case warnings is empty and checkout is allowed to proceed (graceful degradation).
        """
        from decimal import Decimal

        items = cart.get("items", [])
        if not items:
            return [], False

        session_held = self._get_session_held_qty(request, target_date=target_date)
        warnings = []
        checked = 0
        skipped = 0
        for item in items:
            sku = item.get("sku", "")
            qty = int(Decimal(str(item.get("qty", 0))))
            avail = _get_availability(sku, target_date=target_date)
            if avail is None:
                skipped += 1
                continue
            checked += 1
            if avail.get("availability_policy") == "demand_ok" and not avail.get("is_paused", False):
                continue
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
    def _get_session_held_qty(request: HttpRequest, *, target_date=None) -> dict[str, int]:
        session_key = request.session.get("cart_session_key")
        if not session_key:
            return {}
        from shopman.stockman import StockHolds

        holds = StockHolds.find_active_by_reference(session_key)
        held: dict[str, int] = {}
        for hold in holds:
            if target_date is not None and hold.target_date != target_date:
                continue
            held[hold.sku] = held.get(hold.sku, 0) + int(hold.quantity)
        return held

    def _render_with_errors(
        self,
        request,
        cart,
        errors,
        name,
        phone_raw,
        notes,
        extra_form_data=None,
        repricing_warnings=None,
    ):
        form_data = {"name": name, "phone": phone_raw, "notes": notes}
        if extra_form_data:
            form_data.update(extra_form_data)
        ctx = self._checkout_page_context(request, cart)
        ctx["errors"] = errors
        ctx["form_data"] = form_data
        if repricing_warnings:
            ctx["repricing_warnings"] = repricing_warnings
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
