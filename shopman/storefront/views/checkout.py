"""CheckoutView — thin coordinator: interpret → process → present."""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django_ratelimit.decorators import ratelimit

from shopman.shop.services import checkout as checkout_service
from shopman.shop.services.storefront_context import minimum_order_progress

from ..cart import CHANNEL_REF, CartService
from ..intents.checkout import interpret_checkout
from ..services.address_picker import address_picker_context
from .tracking import CepLookupView, OrderConfirmationView  # noqa: F401

logger = logging.getLogger(__name__)


@method_decorator(ensure_csrf_cookie, name="dispatch")
@method_decorator(ratelimit(key="user_or_ip", rate="3/m", method="POST", block=False), name="post")
class CheckoutView(View):
    """Checkout: review order and submit."""

    def get(self, request: HttpRequest) -> HttpResponse:
        cart = CartService.get_cart(request)
        if not cart["items"]:
            return redirect("storefront:cart")

        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return redirect("/login/?next=/checkout/")
        if not customer_info.phone:
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
        checkout_process = checkout_service.process
        try:
            commit_result = checkout_process(
                session_key=intent.session_key,
                channel_ref=intent.channel_ref,
                data=intent.checkout_data,
                idempotency_key=intent.idempotency_key,
            )
        except Exception as exc:
            errors = checkout_service.map_checkout_error(exc)
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
                if checkout_service.order_has_payment_error(order_ref):
                    from django.contrib import messages
                    messages.warning(request, "Pagamento será processado em breve. Acompanhe seu pedido.")
                    return redirect("storefront:order_tracking", ref=order_ref)
            except Exception:
                logger.exception("payment_check_failed for order %s", order_ref)
            if intent.payment_method == "pix" and _starts_payment_after_store_confirmation(intent.channel_ref):
                return redirect("storefront:order_tracking", ref=order_ref)
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
    def _ensure_customer(intent, order_ref: str) -> None:
        try:
            checkout_service.ensure_customer(intent)
        except Exception:
            logger.exception("ensure_customer_failed order=%s", order_ref)

    @staticmethod
    def _persist_new_address(intent, order_ref: str) -> None:
        try:
            checkout_service.persist_new_address(intent)
        except Exception:
            logger.exception("persist_new_address_failed order=%s", order_ref)

    @staticmethod
    def _save_checkout_defaults(request: HttpRequest, intent, order_ref: str) -> None:
        try:
            checkout_service.save_defaults(
                intent,
                order_ref=order_ref,
                enabled=bool(request.POST.get("save_as_default")),
            )
        except Exception:
            logger.exception("save_checkout_defaults_failed order=%s", order_ref)


def _starts_payment_after_store_confirmation(channel_ref: str) -> bool:
    try:
        from shopman.shop.config import ChannelConfig

        return ChannelConfig.for_channel(channel_ref).payment.timing == "post_commit"
    except Exception:
        logger.warning("payment_timing_lookup_failed channel=%s", channel_ref, exc_info=True)
        return False


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

        if not settings.DEBUG:
            raise Http404()

        session_key = CartService._get_session_key(request)
        if not session_key:
            messages.warning(request, "Carrinho vazio — adicione itens antes de simular.")
            return redirect("storefront:cart")

        channel = CartService._get_channel()
        try:
            cart_session = checkout_service.get_open_cart_session(
                session_key=session_key,
                channel_ref=channel.ref,
            )
        except Exception:
            messages.warning(request, "Carrinho não encontrado.")
            return redirect("storefront:cart")

        if not cart_session.items:
            messages.warning(request, "Carrinho vazio — adicione itens antes de simular.")
            return redirect("storefront:cart")

        try:
            order = checkout_service.simulate_ifood_order(cart_session)
        except Exception as e:
            logger.exception("simulate_ifood: ingest failed")
            error_message = getattr(e, "message", str(e))
            messages.error(request, f"Falha ao simular pedido iFood: {error_message}")
            return redirect("storefront:checkout")

        checkout_service.close_cart_session(cart_session)
        request.session.pop("cart_session_key", None)

        messages.success(
            request,
            f"Pedido iFood simulado criado: {order.ref} (external: {order.external_ref}).",
        )
        return redirect("storefront:order_tracking", ref=order.ref)
