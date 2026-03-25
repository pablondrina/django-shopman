from __future__ import annotations

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views import View
from shopman.utils.phone import normalize_phone

from ..constants import HAS_AUTH


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
        verified_phone = request.session.get("storefront_verified_phone")
        is_verified = verified_phone == phone

        from shopman.customers.services import customer as customer_service

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
            "can_verify": HAS_AUTH and not is_verified,
            "is_verified": is_verified,
        })


class RequestCodeView(View):
    """HTMX: request magic code for phone verification during checkout."""

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

        from shopman.auth.services.verification import VerificationService

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

        from shopman.auth.services.verification import VerificationService

        result = VerificationService.verify_for_login(
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

        # Mark session as verified
        request.session["storefront_verified_phone"] = phone
        if result.customer:
            request.session["storefront_verified_name"] = result.customer.name or ""

        return render(request, "storefront/partials/auth_confirmed.html", {
            "phone": phone,
        })
