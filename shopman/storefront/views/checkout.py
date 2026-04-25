"""CheckoutView — thin coordinator: interpret → process → present."""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django_ratelimit.decorators import ratelimit
from shopman.guestman.contrib.loyalty import LoyaltyService

from shopman.storefront.services.checkout_defaults import CheckoutDefaultsService
from shopman.storefront.services.storefront_context import minimum_order_progress

from ..cart import CHANNEL_REF, CartService
from ..intents.checkout import get_payment_methods, interpret_checkout
from ..intents.types import CheckoutIntent
from ..services.address_picker import address_picker_context
from .tracking import CepLookupView, OrderConfirmationView  # noqa: F401

logger = logging.getLogger(__name__)


@method_decorator(ensure_csrf_cookie, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="3/m", method="POST", block=False), name="post")
class CheckoutView(View):
    """Checkout: review order and submit."""

    def _checkout_page_context(self, request: HttpRequest, cart: dict) -> dict:
        """Common context for GET and error re-renders."""
        import json as _json

        from django.conf import settings

        from shopman.shop.models import Shop

        shop = Shop.load()
        shop_defaults = (shop.defaults or {}) if shop else {}
        max_preorder_days = int(shop_defaults.get("max_preorder_days", 30))
        closed_dates = shop_defaults.get("closed_dates", [])

        ctx: dict = {
            "cart": cart,
            "checkout_defaults": {},
            "saved_addresses": [],
            "payment_methods": get_payment_methods(CHANNEL_REF),
            "minimum_order_warning": minimum_order_progress(cart.get("original_subtotal_q") or cart["subtotal_q"]),
            "max_preorder_days": max_preorder_days,
            "closed_dates_json": _json.dumps(closed_dates),
            "debug": settings.DEBUG,
        }

        try:
            from shopman.storefront.services.pickup_slots import annotate_slots_for_checkout
            cart_skus = [item["sku"] for item in cart.get("items", []) if item.get("sku")]
            ctx.update(annotate_slots_for_checkout(cart_skus))
        except Exception:
            logger.exception("pickup_slots_failed")

        customer_info = getattr(request, "customer", None)
        ctx["customer_info"] = customer_info
        ctx["is_verified"] = customer_info is not None
        if customer_info is None:
            return ctx

        from shopman.guestman.services import address as address_service
        from shopman.guestman.services import customer as customer_service

        customer_obj = customer_service.get_by_uuid(customer_info.uuid)
        if customer_obj:
            ctx["saved_addresses"] = [
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
            try:
                checkout_defaults = CheckoutDefaultsService.get_defaults(
                    customer_ref=customer_obj.ref,
                    channel_ref=CHANNEL_REF,
                )
                if checkout_defaults:
                    ctx["checkout_defaults"] = checkout_defaults
            except Exception:
                logger.exception("checkout_defaults_failed")

            try:
                from shopman.utils.monetary import format_money
                balance = LoyaltyService.get_balance(customer_obj.ref)
                ctx["loyalty_balance"] = balance
                ctx["loyalty_value_display"] = f"R$ {format_money(balance)}" if balance > 0 else None
            except Exception:
                logger.exception("loyalty_balance_failed")
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

        from shopman.storefront.projections import build_checkout
        checkout = build_checkout(request=request, channel_ref=CHANNEL_REF)
        return render(request, "storefront/checkout.html", {
            "checkout": checkout,
            "errors": {},
            "form_data": {
                "phone": customer_info.phone or "",
                "name": customer_info.name or "",
            },
            **address_picker_context(
                getattr(checkout, "saved_addresses", ()) or (),
                preselected_id=getattr(checkout, "preselected_address_id", None),
            ),
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        # ── HTTP guards ───────────────────────────────────────────────────
        if getattr(request, "limited", False):
            return render(request, "storefront/partials/rate_limited.html", status=429)

        pre_cart_key = request.session.get("cart_session_key")
        cart = CartService.get_cart(request)
        if not cart["items"]:
            if pre_cart_key and not request.session.get("cart_session_key"):
                from django.contrib import messages
                messages.warning(request, "Seu carrinho expirou. Adicione os itens novamente.")
            return redirect("storefront:cart")

        # ── Interpret ─────────────────────────────────────────────────────
        result = interpret_checkout(request, channel_ref=CHANNEL_REF)
        if result.errors:
            return self._render_with_errors(
                request, cart, result.errors, result.form_data, result.repricing_warnings
            )

        # ── Process ───────────────────────────────────────────────────────
        intent = result.intent
        from shopman.storefront.services.checkout import process as checkout_process
        try:
            commit_result = checkout_process(
                session_key=intent.session_key,
                channel_ref=intent.channel_ref,
                data=intent.checkout_data,
                idempotency_key=intent.idempotency_key,
            )
        except Exception as exc:
            errors = self._map_checkout_error(exc)
            if errors:
                return self._render_with_errors(
                    request, cart, errors, result.form_data, result.repricing_warnings
                )
            raise

        order_ref = commit_result.order_ref

        # ── Post-commit side effects (HTTP concerns) ──────────────────────
        self._ensure_customer(intent, order_ref)
        self._persist_new_address(intent, order_ref)
        self._save_checkout_defaults(request, intent, order_ref)
        request.session.pop("cart_session_key", None)

        # ── Present ───────────────────────────────────────────────────────
        if intent.payment_method in ("pix", "card"):
            try:
                from shopman.orderman.models import Order as _Order
                _order = _Order.objects.get(ref=order_ref)
                if (_order.data or {}).get("payment", {}).get("error"):
                    from django.contrib import messages
                    messages.warning(request, "Pagamento será processado em breve. Acompanhe seu pedido.")
                    return redirect("storefront:order_tracking", ref=order_ref)
            except Exception:
                logger.exception("payment_check_failed for order %s", order_ref)
            return redirect("storefront:order_payment", ref=order_ref)
        return redirect("storefront:order_tracking", ref=order_ref)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _render_with_errors(
        self,
        request: HttpRequest,
        cart: dict,
        errors: dict,
        form_data: dict,
        repricing_warnings: list | None = None,
    ) -> HttpResponse:
        from shopman.storefront.projections import build_checkout
        checkout = build_checkout(request=request, channel_ref=CHANNEL_REF)
        return render(request, "storefront/checkout.html", {
            "checkout": checkout,
            "errors": errors,
            "form_data": form_data,
            "repricing_warnings": repricing_warnings or [],
            **address_picker_context(
                getattr(checkout, "saved_addresses", ()) or (),
                form_data=form_data,
                preselected_id=getattr(checkout, "preselected_address_id", None),
            ),
        })

    @staticmethod
    def _map_checkout_error(exc: Exception) -> dict[str, str] | None:
        from django.core.exceptions import ValidationError as DjangoValidationError
        from shopman.orderman.exceptions import ValidationError as OrderingValidationError

        if isinstance(exc, OrderingValidationError):
            field = "delivery_address" if exc.code == "delivery_zone_not_covered" else "checkout"
            return {field: exc.message}
        if isinstance(exc, DjangoValidationError):
            msgs = exc.messages if hasattr(exc, "messages") else [str(exc)]
            return {"checkout": msgs[0] if msgs else str(exc)}
        return None

    @staticmethod
    def _ensure_customer(intent: CheckoutIntent, order_ref: str) -> None:
        import uuid as uuid_lib

        from django.db import IntegrityError
        from shopman.guestman.services import customer as customer_service

        customer_obj = customer_service.get_by_phone(intent.customer_phone)
        if customer_obj:
            if intent.customer_name and not customer_obj.first_name:
                customer_obj.first_name = intent.customer_name
                customer_obj.save(update_fields=["first_name"])
        else:
            try:
                customer_service.create(
                    ref=f"WEB-{str(uuid_lib.uuid4())[:8].upper()}",
                    first_name=intent.customer_name,
                    phone=intent.customer_phone,
                )
            except IntegrityError:
                pass  # race condition — already created by concurrent request

    @staticmethod
    def _persist_new_address(intent: CheckoutIntent, order_ref: str) -> None:
        """Persist a new delivery address to the customer's address book (omotenashi).

        Skipped when fulfillment is not delivery, a saved address was already used,
        the address text is absent, the customer can't be found, or the exact
        formatted_address already exists in their book.
        """
        if intent.fulfillment_type != "delivery":
            return
        if intent.saved_address_id:
            return
        if not intent.delivery_address:
            return

        try:
            from shopman.guestman.services import address as address_service
            from shopman.guestman.services import customer as customer_service

            customer_obj = customer_service.get_by_phone(intent.customer_phone)
            if not customer_obj:
                return

            if address_service.has_address(customer_obj.ref, intent.delivery_address):
                return

            structured = intent.delivery_address_structured or {}

            lat = structured.get("latitude")
            lng = structured.get("longitude")
            coordinates = (float(lat), float(lng)) if lat and lng else None

            components = {
                "street_number": structured.get("street_number", ""),
                "route": structured.get("route", ""),
                "neighborhood": structured.get("neighborhood", ""),
                "city": structured.get("city", ""),
                "state_code": structured.get("state_code", ""),
                "postal_code": structured.get("postal_code", ""),
            }

            is_first = not address_service.has_any_address(customer_obj.ref)

            address_service.add_address(
                customer_ref=customer_obj.ref,
                label="other",
                label_custom="Entrega",
                formatted_address=intent.delivery_address,
                place_id=structured.get("place_id") or None,
                components=components,
                coordinates=coordinates,
                complement=structured.get("complement", ""),
                delivery_instructions=structured.get("delivery_instructions", ""),
                is_default=is_first,
            )
        except Exception:
            logger.exception("persist_new_address_failed order=%s", order_ref)

    def _save_checkout_defaults(
        self, request: HttpRequest, intent: CheckoutIntent, order_ref: str
    ) -> None:
        if not request.POST.get("save_as_default"):
            return
        from shopman.guestman.services import customer as customer_service
        customer_obj = customer_service.get_by_phone(intent.customer_phone)
        if not customer_obj:
            return
        try:
            defaults_data: dict = {
                "fulfillment_type": intent.fulfillment_type,
                "payment_method": intent.payment_method,
            }
            if intent.fulfillment_type == "delivery":
                if intent.saved_address_id:
                    defaults_data["delivery_address_id"] = intent.saved_address_id
                if intent.delivery_time_slot:
                    defaults_data["delivery_time_slot"] = intent.delivery_time_slot
            if intent.notes:
                defaults_data["order_notes"] = intent.notes
            CheckoutDefaultsService.save_defaults(
                customer_ref=customer_obj.ref,
                channel_ref=CHANNEL_REF,
                data=defaults_data,
                source=f"order:{order_ref}",
            )
        except Exception:
            logger.exception("save_checkout_defaults_failed order=%s", order_ref)


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
                "minimum_order_warning": minimum_order_progress(cart.get("original_subtotal_q") or cart["subtotal_q"]),
            },
        )


@method_decorator(csrf_exempt, name="dispatch")
class SimulateIFoodView(View):
    """Dev-only: translate current cart Session into an iFood payload and ingest it.

    Gated behind ``settings.DEBUG`` so it never ships to production. Builds a
    canonical iFood payload from the open Session via ``session_to_ifood_payload``
    and hands it to ``ifood_ingest.ingest`` — the exact same entry point a real
    iFood webhook would use. The storefront cart Session is then closed so the
    user gets a fresh cart (the simulated order lives on the iFood channel and
    is unrelated to the storefront checkout flow).

    CSRF-exempt on purpose: this endpoint *simulates* an iFood webhook, and real
    webhook endpoints never carry Django CSRF tokens (external services don't
    know about them). Keeping this consistent with what it simulates avoids the
    mismatch that caused the dev form to 403 when submitted from the browser.
    Safe because the view is hard-gated behind ``settings.DEBUG`` and only acts
    on the caller's own open cart Session.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        from django.conf import settings
        from django.contrib import messages
        from django.http import Http404
        from shopman.orderman.models import Session

        from shopman.shop.services import ifood_ingest
        from shopman.storefront.services.ifood_simulation import session_to_ifood_payload

        if not settings.DEBUG:
            raise Http404()

        session_key = CartService._get_session_key(request)
        if not session_key:
            messages.warning(request, "Carrinho vazio — adicione itens antes de simular.")
            return redirect("storefront:cart")

        channel = CartService._get_channel()
        try:
            cart_session = Session.objects.get(
                session_key=session_key,
                channel_ref=channel.ref,
                state="open",
            )
        except Session.DoesNotExist:
            messages.warning(request, "Carrinho não encontrado.")
            return redirect("storefront:cart")

        if not cart_session.items:
            messages.warning(request, "Carrinho vazio — adicione itens antes de simular.")
            return redirect("storefront:cart")

        try:
            payload = session_to_ifood_payload(cart_session)
            order = ifood_ingest.ingest(payload)
        except ifood_ingest.IFoodIngestError as e:
            logger.exception("simulate_ifood: ingest failed")
            messages.error(request, f"Falha ao simular pedido iFood: {e.message}")
            return redirect("storefront:checkout")
        except Exception as e:
            logger.exception("simulate_ifood: unexpected error")
            messages.error(request, f"Erro inesperado: {e}")
            return redirect("storefront:checkout")

        cart_session.state = "closed"
        cart_session.save(update_fields=["state", "updated_at"])
        request.session.pop("cart_session_key", None)

        messages.success(
            request,
            f"Pedido iFood simulado criado: {order.ref} (external: {order.external_ref}).",
        )
        return redirect("storefront:order_tracking", ref=order.ref)
