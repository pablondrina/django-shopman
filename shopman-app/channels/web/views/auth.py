from __future__ import annotations

import logging

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from shopman.utils.phone import normalize_phone

from ..constants import HAS_AUTH

logger = logging.getLogger("shopman.web.auth")

# Session keys for storefront auth
SESSION_CUSTOMER_UUID = "storefront_customer_uuid"
SESSION_VERIFIED = "storefront_verified"
SESSION_VERIFIED_PHONE = "storefront_verified_phone"
SESSION_VERIFIED_NAME = "storefront_verified_name"

# Rate limit settings
RATE_LIMIT_REQUEST_CODE_MAX = 3
RATE_LIMIT_REQUEST_CODE_WINDOW = 600  # 10 min
RATE_LIMIT_VERIFY_CODE_MAX = 5
RATE_LIMIT_VERIFY_CODE_WINDOW = 600  # 10 min


def _set_auth_session(request: HttpRequest, customer, phone: str) -> None:
    """Set session vars after successful authentication."""
    request.session[SESSION_CUSTOMER_UUID] = str(customer.uuid)
    request.session[SESSION_VERIFIED] = True
    request.session[SESSION_VERIFIED_PHONE] = phone
    request.session[SESSION_VERIFIED_NAME] = customer.name or ""


def get_authenticated_customer(request: HttpRequest):
    """Get customer from session if authenticated.

    Returns the Customer model instance or None.
    """
    customer_uuid = request.session.get(SESSION_CUSTOMER_UUID)
    verified = request.session.get(SESSION_VERIFIED, False)
    if not customer_uuid or not verified:
        return None

    from shopman.customers.services import customer as customer_service

    return customer_service.get_by_uuid(customer_uuid)


def _check_rate_limit(key: str, max_requests: int, window: int) -> bool:
    """Check rate limit using Django cache. Returns True if allowed."""
    cache_key = f"rl:{key}"
    count = cache.get(cache_key, 0)
    if count >= max_requests:
        return False
    cache.set(cache_key, count + 1, window)
    return True


class CustomerLookupView(View):
    """HTMX/JSON: lookup customer by phone, return name + saved addresses."""

    def get(self, request: HttpRequest) -> HttpResponse:
        phone_raw = request.GET.get("phone", "").strip()
        if not phone_raw:
            return JsonResponse({"found": False})

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            return JsonResponse({"found": False})

        # Check if already verified in this session
        verified_phone = request.session.get(SESSION_VERIFIED_PHONE)
        is_verified = verified_phone == phone

        from shopman.customers.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)
        if not customer:
            return JsonResponse({"found": False, "can_verify": False})

        # Only expose PII (name, addresses) if session is verified for this phone
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


class RequestCodeView(View):
    """HTMX: request verification code for phone verification during checkout."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if not HAS_AUTH:
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

        # Rate limit: max 3 requests per phone per 10 min
        if not _check_rate_limit(
            f"req_code:{phone}",
            RATE_LIMIT_REQUEST_CODE_MAX,
            RATE_LIMIT_REQUEST_CODE_WINDOW,
        ):
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": "Muitas tentativas. Aguarde alguns minutos.",
                "phone": phone,
                "can_retry": False,
            })

        from shopman.auth.services.verification import AuthService

        ip = request.META.get("REMOTE_ADDR")
        result = AuthService.request_code(
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
    """HTMX: verify verification code for phone during checkout."""

    def post(self, request: HttpRequest) -> HttpResponse:
        if not HAS_AUTH:
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

        # Rate limit: max 5 verify attempts per phone per 10 min
        if not _check_rate_limit(
            f"verify_code:{phone}",
            RATE_LIMIT_VERIFY_CODE_MAX,
            RATE_LIMIT_VERIFY_CODE_WINDOW,
        ):
            return render(request, "storefront/partials/auth_error.html", {
                "error_message": "Muitas tentativas. Aguarde alguns minutos.",
                "phone": phone,
                "can_retry": False,
            })

        from shopman.auth.services.verification import AuthService

        result = AuthService.verify_for_login(
            target_value=phone,
            code_input=code_input,
            request=request,
        )

        if not result.success:
            # Translate Auth error messages to PT-BR
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

        # Set session-based auth
        _set_auth_session(request, result.customer, phone)

        # Trust device (set cookie for skip-OTP on next visit)
        response = render(request, "storefront/partials/auth_confirmed.html", {
            "phone": phone,
        })

        from shopman.auth.services.device_trust import DeviceTrustService

        DeviceTrustService.trust_device(
            response=response,
            customer_id=result.customer.uuid,
            request=request,
        )

        return response


class BridgeLoginView(View):
    """Consume an access link and create an authenticated session.

    URL: /auth/bridge/<token>/
    Flow: WhatsApp link → this view → session created → redirect
    """

    def get(self, request: HttpRequest, token: str) -> HttpResponse:
        if not HAS_AUTH:
            return redirect("/")

        from shopman.auth.services.access_link import AccessLinkService
        from shopman.auth.utils import safe_redirect_url

        result = AccessLinkService.exchange(
            token_str=token,
            request=request,
            preserve_session_keys=["cart"],
        )

        if not result.success:
            logger.warning("Access link exchange failed: %s", result.error)
            return render(request, "storefront/bridge_invalid.html", {
                "error": result.error,
            })

        # Set storefront session vars from the authenticated customer
        if result.customer:
            phone = result.customer.phone or ""
            request.session[SESSION_CUSTOMER_UUID] = str(result.customer.uuid)
            request.session[SESSION_VERIFIED] = True
            request.session[SESSION_VERIFIED_PHONE] = phone
            request.session[SESSION_VERIFIED_NAME] = result.customer.name or ""

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

        phone_raw = request.POST.get("phone", "").strip()
        if not phone_raw:
            return JsonResponse({"trusted": False})

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            return JsonResponse({"trusted": False})

        from shopman.customers.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)
        if not customer:
            return JsonResponse({"trusted": False})

        from shopman.auth.services.device_trust import DeviceTrustService

        if DeviceTrustService.check_device_trust(request, customer.uuid):
            _set_auth_session(request, customer, phone)

            # AUTH-6A: Dual write — also set request.user via Django login
            from django.contrib.auth import login

            from shopman.auth.protocols.customer import AuthCustomerInfo
            from shopman.auth.services._user_bridge import get_or_create_user_for_customer

            customer_info = AuthCustomerInfo(
                uuid=customer.uuid,
                name=customer.name,
                phone=customer.phone,
                email=getattr(customer, "email", None) or None,
                is_active=True,
            )
            user, _ = get_or_create_user_for_customer(customer_info)
            login(request, user, backend="shopman.auth.backends.PhoneOTPBackend")

            return JsonResponse({"trusted": True, "name": customer.name})

        return JsonResponse({"trusted": False})
