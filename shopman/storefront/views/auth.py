from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django_ratelimit.decorators import ratelimit
from shopman.utils.phone import normalize_phone

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

    from shopman.guestman.services import customer as customer_service

    return customer_service.get_by_uuid(customer_info.uuid)


class LoginView(View):
    """Dedicated login page: phone → OTP → logged in → redirect to ?next="""

    def get(self, request: HttpRequest) -> HttpResponse:
        next_url = request.GET.get("next", "")
        step = request.GET.get("step", "")

        # Post-login: server decides based on real state (not stale session flag)
        if step == "post-login":
            phone = request.session.get("login_phone", "")
            if phone:
                from shopman.guestman.services import customer as customer_service

                customer = customer_service.get_by_phone(phone)
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
            try:
                from shopman.doorman import TrustedDevice
                from shopman.doorman.conf import doorman_settings
                raw_token = request.COOKIES.get(doorman_settings.DEVICE_TRUST_COOKIE_NAME)
                if raw_token:
                    device = TrustedDevice.verify_token(raw_token)
                    if device:
                        from shopman.guestman.services import customer as customer_service
                        trusted_customer = customer_service.get_by_uuid(device.customer_id)
                        if trusted_customer:
                            phone_prefill = trusted_customer.phone or ""
                            trusted_name = trusted_customer.first_name or ""
            except Exception:
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
            "phone_prefill": phone_prefill,
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
            })

        intent = result.intent
        phone = intent.phone
        delivery_method = intent.delivery_method

        from shopman.guestman.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)

        if HAS_AUTH:
            from shopman.doorman.services.verification import AuthService

            auth_result = AuthService.request_code(
                target_value=phone,
                purpose="login",
                delivery_method=delivery_method,
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            # WhatsApp failed → auto-fallback to SMS
            if not auth_result.success and delivery_method == "whatsapp":
                logger.info("WhatsApp delivery failed for %s, falling back to SMS", phone)
                delivery_method = "sms"
                auth_result = AuthService.request_code(
                    target_value=phone,
                    purpose="login",
                    delivery_method="sms",
                    ip_address=request.META.get("REMOTE_ADDR"),
                )

            if not auth_result.success:
                return render(request, "storefront/login.html", {
                    "step": "phone",
                    "error": "Não foi possível enviar o código. Verifique o número e tente novamente.",
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

        from shopman.guestman.services import customer as customer_service

        customer_obj = customer_service.get_by_phone(phone)
        if customer_obj and not customer_obj.first_name:
            customer_obj.first_name = intent.name
            customer_obj.save(update_fields=["first_name"])

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

        from shopman.guestman.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)
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

        from shopman.doorman.services.verification import AuthService

        auth_result = AuthService.request_code(
            target_value=phone,
            purpose="login",
            delivery_method="whatsapp",
            ip_address=request.META.get("REMOTE_ADDR"),
        )

        if not auth_result.success:
            _send_translations = {
                "Too many attempts. Please wait a few minutes.": "Muitas tentativas. Aguarde alguns minutos.",
                "Please wait before requesting a new code.": "Aguarde antes de solicitar um novo código.",
                "Too many attempts from this location.": "Muitas tentativas deste local.",
                "Failed to send code.": "Falha ao enviar código.",
                "Error sending code.": "Erro ao enviar código.",
            }
            raw = auth_result.error or ""
            error_msg = _send_translations.get(raw, raw) or "Erro ao enviar código."
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

        from shopman.doorman.services.verification import AuthService

        auth_result = AuthService.verify_for_login(
            target_value=phone,
            code_input=code_input,
            request=request,
        )

        if not auth_result.success:
            _error_translations = {
                "Incorrect code.": "Código incorreto.",
                "Code expired. Please request a new one.": "Código expirado. Solicite um novo.",
                "Account not found. Please contact support.": "Conta não encontrada.",
            }
            raw_error = auth_result.error or ""
            error_msg = _error_translations.get(raw_error, raw_error) or "Código inválido."
            if auth_result.attempts_remaining is not None and auth_result.attempts_remaining > 0:
                error_msg += f" ({auth_result.attempts_remaining} tentativa(s) restante(s))"
            return render(request, "storefront/partials/auth_verify_code.html", {
                "phone": phone,
                "error_message": error_msg,
            })

        # Django auth already called by verify_for_login(request=request)
        # Resolve customer name to pass explicitly — omotenashi_ctx.customer_name is
        # None at this point because AuthCustomerMiddleware ran before auth happened.
        confirmed_name = ""
        try:
            from shopman.guestman.services import customer as customer_service
            confirmed_customer = customer_service.get_by_uuid(auth_result.customer.uuid)
            if confirmed_customer:
                confirmed_name = confirmed_customer.first_name or ""
        except Exception:
            logger.debug("auth_confirmed_name_lookup_failed", exc_info=True)

        # Trust device (set cookie for skip-OTP on next visit)
        response = render(request, "storefront/partials/auth_confirmed.html", {
            "phone": phone,
            "customer_name": confirmed_name,
        })

        from shopman.doorman.services.device_trust import DeviceTrustService

        DeviceTrustService.trust_device(
            response=response,
            customer_id=auth_result.customer.uuid,
            request=request,
        )

        return response


class AccessLinkLoginView(View):
    """Consume an access link and create an authenticated session.

    URL: /auth/access/<token>/
    Flow: WhatsApp link → this view → session created → redirect
    """

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        if not HAS_AUTH:
            return redirect("/")

        from shopman.doorman.services.access_link import AccessLinkService
        from shopman.doorman.utils import safe_redirect_url

        result = AccessLinkService.exchange(
            token_str=token,
            request=request,
            preserve_session_keys=["cart"],
        )

        if not result.success:
            logger.warning("Access link exchange failed: %s", result.error)
            return render(request, "storefront/access_link_invalid.html", {
                "error": result.error,
            })

        # Django auth already called by AccessLinkService.exchange(request=request)
        # Redirect based on token audience or next param
        next_url = safe_redirect_url(request.GET.get("next"), request)
        return redirect(next_url)


class DeviceCheckLoginView(View):
    """Check if device is trusted and auto-login if so.

    Called from account page to attempt skip-OTP login.
    Returns JSON for HTMX consumption.
    """

    def post(self, request: HttpRequest) -> HttpResponse:
        if not HAS_AUTH:
            return JsonResponse({"trusted": False})

        result = interpret_device_check_login(request)
        if result.intent is None:
            return JsonResponse({"trusted": False})

        phone = result.intent.phone

        from shopman.guestman.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)
        if not customer:
            return JsonResponse({"trusted": False})

        from shopman.doorman.services.device_trust import DeviceTrustService

        if DeviceTrustService.check_device_trust(request, customer.uuid):
            from django.contrib.auth import login
            from shopman.doorman.protocols.customer import AuthCustomerInfo
            from shopman.doorman.services._user_bridge import get_or_create_user_for_customer

            customer_info = AuthCustomerInfo(
                uuid=customer.uuid,
                name=customer.name,
                phone=customer.phone,
                email=getattr(customer, "email", None) or None,
                is_active=True,
            )
            user, _ = get_or_create_user_for_customer(customer_info)
            login(request, user, backend="shopman.doorman.backends.PhoneOTPBackend")

            return JsonResponse({"trusted": True, "name": customer.name})

        return JsonResponse({"trusted": False})
