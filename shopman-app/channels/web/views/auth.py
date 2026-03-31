from __future__ import annotations

import logging

from django.core.cache import cache
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views import View
from shopman.utils.phone import normalize_phone

from ..constants import HAS_AUTH

logger = logging.getLogger("shopman.web.auth")

# Rate limit settings
RATE_LIMIT_REQUEST_CODE_MAX = 3
RATE_LIMIT_REQUEST_CODE_WINDOW = 600  # 10 min
RATE_LIMIT_VERIFY_CODE_MAX = 5
RATE_LIMIT_VERIFY_CODE_WINDOW = 600  # 10 min


def get_authenticated_customer(request: HttpRequest):
    """Get customer from authenticated request.

    Reads from request.customer (set by AuthCustomerMiddleware).
    Returns the Customer model instance or None.
    """
    customer_info = getattr(request, "customer", None)
    if customer_info is None:
        return None

    from shopman.customers.services import customer as customer_service

    return customer_service.get_by_uuid(customer_info.uuid)


def _check_rate_limit(key: str, max_requests: int, window: int) -> bool:
    """Check rate limit using Django cache. Returns True if allowed."""
    cache_key = f"rl:{key}"
    count = cache.get(cache_key, 0)
    if count >= max_requests:
        return False
    cache.set(cache_key, count + 1, window)
    return True


def _normalize_phone_with_ddd(phone_raw: str) -> str:
    """
    Normalize phone to E.164 via libphonenumber.

    Single fallback: if input has 8-9 digits (no DDD), prepend the shop's default DDD.
    Everything else is handled by normalize_phone / libphonenumber — no heuristics.
    """
    from ..constants import get_default_ddd

    phone = normalize_phone(phone_raw)
    if phone:
        return phone

    # Only fallback: short number without DDD
    digits = "".join(c for c in phone_raw if c.isdigit())
    if 8 <= len(digits) <= 9:
        return normalize_phone(f"{get_default_ddd()}{digits}")

    return ""


class LoginView(View):
    """Dedicated login page: phone → OTP → logged in → redirect to ?next="""

    def get(self, request: HttpRequest) -> HttpResponse:
        next_url = request.GET.get("next", "")
        step = request.GET.get("step", "")

        # Post-login: server decides based on real state (not stale session flag)
        if step == "post-login":
            phone = request.session.get("login_phone", "")
            if phone:
                from shopman.customers.services import customer as customer_service

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

        return render(request, "storefront/login.html", {
            "step": "phone",
            "next": next_url,
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        next_url = request.GET.get("next", request.POST.get("next", ""))
        step = request.POST.get("step", "phone")

        if step == "phone":
            return self._handle_phone(request, next_url)
        elif step == "name":
            return self._handle_name(request, next_url)

        return redirect("storefront:login")

    def _handle_phone(self, request, next_url):
        phone_raw = request.POST.get("phone", "").strip()
        delivery_method = request.POST.get("delivery_method", "whatsapp")
        if delivery_method not in ("whatsapp", "sms"):
            delivery_method = "whatsapp"

        if not phone_raw:
            return render(request, "storefront/login.html", {
                "step": "phone",
                "error": "Telefone é obrigatório.",
                "next": next_url,
            })

        try:
            phone = _normalize_phone_with_ddd(phone_raw)
        except Exception:
            logger.warning("Phone normalization failed", extra={"phone_raw": phone_raw})
            phone = ""

        if not phone:
            return render(request, "storefront/login.html", {
                "step": "phone",
                "error": "Telefone inválido. Informe com DDD, ex: (43) 99999-9999",
                "phone_value": phone_raw,
                "next": next_url,
            })

        # Check if customer exists
        from shopman.customers.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)

        # Send OTP code
        if not _check_rate_limit(f"login_req:{phone}", RATE_LIMIT_REQUEST_CODE_MAX, RATE_LIMIT_REQUEST_CODE_WINDOW):
            return render(request, "storefront/login.html", {
                "step": "phone",
                "error": "Muitas tentativas. Aguarde alguns minutos.",
                "phone_value": phone_raw,
                "next": next_url,
            })

        if HAS_AUTH:
            from shopman.auth.services.verification import AuthService

            result = AuthService.request_code(
                target_value=phone,
                purpose="login",
                delivery_method=delivery_method,
                ip_address=request.META.get("REMOTE_ADDR"),
            )

            # WhatsApp failed → auto-fallback to SMS
            if not result.success and delivery_method == "whatsapp":
                logger.info("WhatsApp delivery failed for %s, falling back to SMS", phone)
                delivery_method = "sms"
                result = AuthService.request_code(
                    target_value=phone,
                    purpose="login",
                    delivery_method="sms",
                    ip_address=request.META.get("REMOTE_ADDR"),
                )

            if not result.success:
                return render(request, "storefront/login.html", {
                    "step": "phone",
                    "error": "Não foi possível enviar o código. Verifique o número e tente novamente.",
                    "phone_value": phone_raw,
                    "next": next_url,
                })

        # Store phone in session for post-login name step
        request.session["login_phone"] = phone

        return render(request, "storefront/login.html", {
            "step": "code",
            "phone_value": phone,
            "customer_name": customer.first_name if customer else "",
            "delivery_method": delivery_method,
            "next": next_url,
        })

    def _handle_name(self, request, next_url):
        """After OTP for new customers: save name and redirect."""
        phone = request.session.get("login_phone", "")
        name = request.POST.get("name", "").strip()

        if not name:
            return render(request, "storefront/login.html", {
                "step": "name",
                "phone_value": phone,
                "error": "Nome é obrigatório.",
                "next": next_url,
            })

        # Update customer name
        from shopman.customers.services import customer as customer_service

        customer_obj = customer_service.get_by_phone(phone)
        if customer_obj and not customer_obj.first_name:
            customer_obj.first_name = name
            customer_obj.save(update_fields=["first_name"])

        # Clean up session
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
            logger.warning("Phone normalization failed in lookup", extra={"phone_raw": phone_raw})
            return JsonResponse({"found": False})

        # Check if authenticated for this phone
        customer_info = getattr(request, "customer", None)
        is_verified = customer_info is not None and customer_info.phone == phone

        from shopman.customers.services import customer as customer_service

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
            logger.warning("Phone normalization failed", extra={"phone_raw": phone_raw})
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
            logger.warning("Phone normalization failed", extra={"phone_raw": phone_raw})
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

        # Django auth already called by verify_for_login(request=request)
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


class AccessLinkLoginView(View):
    """Consume an access link and create an authenticated session.

    URL: /auth/access/<token>/
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

        phone_raw = request.POST.get("phone", "").strip()
        if not phone_raw:
            return JsonResponse({"trusted": False})

        try:
            phone = normalize_phone(phone_raw)
        except Exception:
            logger.warning("Phone normalization failed in device check", extra={"phone_raw": phone_raw})
            return JsonResponse({"trusted": False})

        from shopman.customers.services import customer as customer_service

        customer = customer_service.get_by_phone(phone)
        if not customer:
            return JsonResponse({"trusted": False})

        from shopman.auth.services.device_trust import DeviceTrustService

        if DeviceTrustService.check_device_trust(request, customer.uuid):
            # Django login
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
