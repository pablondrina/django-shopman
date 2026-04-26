from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django_ratelimit.decorators import ratelimit
from shopman.utils.phone import normalize_phone

from shopman.shop.services import auth as auth_service

from ..constants import HAS_AUTH
from ..intents.auth import (
    interpret_device_check_login,
    interpret_login,
    interpret_request_code,
    interpret_verify_code,
)

logger = logging.getLogger("shopman.storefront.views.auth")


def get_authenticated_customer(request: HttpRequest):
    """Get customer from authenticated request.

    Reads from request.customer (set by AuthCustomerMiddleware).
    Returns the Customer model instance or None.
    """
    customer_info = getattr(request, "customer", None)
    if customer_info is None:
        return None

    return auth_service.customer_by_uuid(customer_info.uuid)


class LoginView(View):
    """Dedicated login page: phone → OTP → logged in → redirect to ?next="""

    def get(self, request: HttpRequest) -> HttpResponse:
        next_url = request.GET.get("next", "")
        step = request.GET.get("step", "")

        # Post-login: server decides based on real state (not stale session flag)
        if step == "post-login":
            phone = request.session.get("login_phone", "")
            if phone:
                customer = auth_service.customer_by_phone(phone)
                if customer and customer.first_name:
                    # Existing customer with name → done
                    request.session.pop("login_phone", None)
                    request.session.pop("login_is_new", None)
                    return redirect(next_url or "/")
                # New or nameless customer → ask for name
                return render(request, "storefront/login.html", {
                    "step": "name",
                    "phone_value": phone,
                    "next": next_url,
                })
            return redirect(next_url or "/")

        # Name step for new customers (after OTP)
        if step == "name":
            phone = request.session.get("login_phone", "")
            return render(request, "storefront/login.html", {
                "step": "name",
                "phone_value": phone,
                "next": next_url,
            })

        # Already logged in → redirect
        if getattr(request, "customer", None) is not None:
            return redirect(next_url or "/")

        # Device trust pre-fill (F-03): if a trusted-device cookie exists, look up
        # the associated customer so we can pre-fill the phone and greet by name.
        phone_prefill = ""
        trusted_name = ""
        if HAS_AUTH:
            phone_prefill, trusted_name = auth_service.trusted_device_prefill(request)
            if not phone_prefill and not trusted_name:
                logger.debug("device_trust_prefill_failed", exc_info=True)

        # login_context drives copy variation in the template (F-10)
        if trusted_name:
            login_context = "trusted"
        elif next_url and "checkout" in next_url:
            login_context = "checkout"
        else:
            login_context = "direct"

        return render(request, "storefront/login.html", {
            "step": "phone",
            "next": next_url,
            "phone_value": phone_prefill,
            "trusted_name": trusted_name,
            "login_context": login_context,
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        step = request.POST.get("step", "phone")

        if step == "phone":
            return self._handle_phone(request)
        elif step == "name":
            return self._handle_name(request)

        return redirect("storefront:login")

    def _handle_phone(self, request):
        result = interpret_login(request)
        next_url = result.form_data.get("next", "")

        if result.intent is None:
            error = list(result.errors.values())[0] if result.errors else ""
            return render(request, "storefront/login.html", {
                "step": "phone",
                "error": error,
                "phone_value": result.form_data.get("phone", ""),
                "next": next_url,
                "trusted_name": "",
                "login_context": "checkout" if "checkout" in next_url else "direct",
            })

        intent = result.intent
        phone = intent.phone
        delivery_method = intent.delivery_method

        customer = auth_service.customer_by_phone(phone)

        if HAS_AUTH:
            auth_result = auth_service.request_code(
                phone=phone,
                delivery_method=delivery_method,
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            if not auth_result.success:
                error_msg = auth_service.request_code_error_message(auth_result)
                return render(request, "storefront/login.html", {
                    "step": "phone",
                    "error": error_msg,
                    "phone_value": result.form_data.get("phone", ""),
                    "next": next_url,
                })

        request.session["login_phone"] = phone

        return render(request, "storefront/login.html", {
            "step": "code",
            "phone_value": phone,
            "customer_name": customer.first_name if customer else "",
            "delivery_method": delivery_method,
            "next": next_url,
        })

    def _handle_name(self, request):
        result = interpret_login(request)
        next_url = result.form_data.get("next", "")

        if result.intent is None:
            error = list(result.errors.values())[0] if result.errors else ""
            phone = request.session.get("login_phone", "")
            return render(request, "storefront/login.html", {
                "step": "name",
                "phone_value": phone,
                "error": error,
                "next": next_url,
            })

        intent = result.intent
        phone = request.session.get("login_phone", "")

        auth_service.set_missing_first_name(phone=phone, name=intent.name)

        request.session.pop("login_phone", None)

        return redirect(next_url or "/")


class CustomerLookupView(View):
    """HTMX/JSON: lookup customer by phone, return name + saved addresses."""

    def get(self, request: HttpRequest) -> HttpResponse:
        phone_raw = request.GET.get("phone", "").strip()
        if not phone_raw:
            return JsonResponse({"found": False})

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            logger.exception("Phone normalization failed in lookup for raw input")
            return JsonResponse({"found": False})

        # Check if authenticated for this phone
        customer_info = getattr(request, "customer", None)
        is_verified = customer_info is not None and customer_info.phone == phone

        customer = auth_service.customer_by_phone(phone)
        if not customer:
            return JsonResponse({"found": False, "can_verify": False})

        # Only expose PII (name, addresses) if verified for this phone
        if is_verified:
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
                "can_verify": False,
                "is_verified": True,
            })

        # Not verified — only confirm existence, no PII
        return JsonResponse({
            "found": True,
            "name": "",
            "phone": "",
            "addresses": [],
            "can_verify": HAS_AUTH,
            "is_verified": False,
        })


@method_decorator(ratelimit(key="post:phone", rate="5/m", method="POST", block=False), name="post")
class RequestCodeView(View):
    """HTMX: request verification code for phone verification during checkout."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if not HAS_AUTH:
            return HttpResponse("")

        if getattr(request, "limited", False):
            return render(request, "storefront/partials/rate_limited.html", status=429)

        result = interpret_request_code(request)
        if result.intent is None:
            error_msg = list(result.errors.values())[0] if result.errors else "Telefone inválido."
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": error_msg,
            })

        phone = result.intent.phone

        auth_result = auth_service.request_code(
            phone=phone,
            delivery_method="whatsapp",
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        if not auth_result.success:
            error_msg = auth_service.request_code_partial_error_message(auth_result)
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": error_msg,
                "phone": phone,
                "can_retry": "aguarde" not in error_msg.lower(),
            })

        return render(request, "storefront/partials/auth_verify_code.html", {
            "phone": phone,
        })


@method_decorator(ratelimit(key="post:phone", rate="10/m", method="POST", block=False), name="post")
class VerifyCodeView(View):
    """HTMX: verify verification code for phone during checkout."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if not HAS_AUTH:
            return HttpResponse("")

        if getattr(request, "limited", False):
            return render(request, "storefront/partials/rate_limited.html", status=429)

        result = interpret_verify_code(request)
        if result.intent is None:
            error_msg = list(result.errors.values())[0] if result.errors else "Código inválido."
            phone = result.form_data.get("phone", "")
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": error_msg,
                "phone": phone,
            })

        phone = result.intent.phone
        code_input = result.intent.code

        auth_result = auth_service.verify_for_login(
            phone=phone,
            code_input=code_input,
            request=request,
        )

        if not auth_result.success:
            error_msg = auth_service.verify_error_message(auth_result)
            return render(request, "storefront/partials/auth_verify_code.html", {
                "phone": phone,
                "error_message": error_msg,
            })

        # Django auth already called by verify_for_login(request=request)
        # Resolve customer name to pass explicitly — omotenashi_ctx.customer_name is
        # None at this point because AuthCustomerMiddleware ran before auth happened.
        confirmed_name = auth_service.confirmed_customer_name(auth_result)
        if not confirmed_name:
            logger.debug("auth_confirmed_name_lookup_failed", exc_info=True)

        # Render confirmation — trust decision deferred to user via TrustDeviceView
        return render(request, "storefront/partials/auth_confirmed.html", {
            "phone": phone,
            "customer_name": confirmed_name,
        })


class AccessLinkLoginView(View):
    """Consume an access link and create an authenticated session.

    URL: /auth/access/<token>/
    Lifecycle: WhatsApp link → this view → session created → redirect
    """

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        if not HAS_AUTH:
            return redirect("/")

        result = auth_service.exchange_access_link(token=token, request=request)

        if not result.success:
            logger.warning("Access link exchange failed: %s", result.error)
            return render(request, "storefront/access_link_invalid.html", {
                "error": result.error,
            })

        # Django auth already called by AccessLinkService.exchange(request=request)
        # Redirect based on token audience or next param
        next_url = auth_service.safe_redirect_url(request.GET.get("next"), request)
        return redirect(next_url)


class DeviceCheckLoginView(View):
    """HTMX: auto-login via device trust and show greeting, or 204 to fall through.

    Fires on button click from login.html when a trusted-device cookie is present.
    If trusted, logs the user in and returns auth_trusted_greeting.html (greeting +
    delayed redirect).  If not trusted, returns 204 so HTMX skips the swap and the
    normal phone form stays visible.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        if not HAS_AUTH:
            return HttpResponse(status=204)

        result = interpret_device_check_login(request)
        if result.intent is None:
            return HttpResponse(status=204)

        phone = result.intent.phone

        customer = auth_service.trusted_device_login(request, phone=phone)
        if not customer:
            return HttpResponse(status=204)

        next_url = request.POST.get("next", "")
        return render(request, "storefront/partials/auth_trusted_greeting.html", {
            "customer_name": customer.first_name or customer.name,
            "next_url": next_url,
        })


class TrustDeviceView(View):
    """HTMX: set device trust cookie after OTP login.

    Called from auth_confirmed.html with hx-swap="none". Sets the trust cookie
    and returns 200; client-side Alpine handles the redirect on success.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        if not HAS_AUTH:
            return HttpResponse(
                '<div x-data x-init="window.dispatchEvent(new CustomEvent(\'auth-confirmed\'))"></div>'
            )

        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return HttpResponse(
                '<div x-data x-init="window.dispatchEvent(new CustomEvent(\'auth-confirmed\'))"></div>'
            )

        trust = request.POST.get("trust", "0") == "1"

        if trust:
            response = render(request, "storefront/partials/auth_device_saved.html")
            auth_service.trust_device(
                response=response,
                customer_id=customer_info.uuid,
                request=request,
            )
            return response

        return HttpResponse(
            '<div x-data x-init="window.dispatchEvent(new CustomEvent(\'auth-confirmed\'))"></div>'
        )
