"""
Verification code views.
"""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.views import View

from ..conf import get_auth_settings
from ..models import AccessLink, VerificationCode
from ..services.access_link import AccessLinkService
from ..services.verification import AuthService
from ..utils import get_client_ip, normalize_phone, safe_redirect_url

logger = logging.getLogger("shopman.doorman.views.verification_code")


class VerificationCodeRequestView(View):
    """
    Request a verification code.

    GET /doorman/code/request
        Renders code_request.html form

    POST /doorman/code/request
        Form data: phone=...
        JSON data: {"phone": "..."}

    On success (form): Redirects to code-verify
    On success (JSON): Returns {"success": true, "phone": "..."}
    """

    def get_template_name(self):
        """Get template name from settings."""
        settings = get_auth_settings()
        return settings.TEMPLATE_CODE_REQUEST

    def get(self, request):
        context = {
            "next": request.GET.get("next", ""),
        }
        return render(request, self.get_template_name(), context)

    def post(self, request):
        template_name = self.get_template_name()

        # Parse input
        is_json = request.content_type == "application/json"

        if is_json:
            try:
                data = json.loads(request.body)
                phone_raw = data.get("phone", "")
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)
        else:
            phone_raw = request.POST.get("phone", "")

        # Validate phone
        if not phone_raw:
            error = str(_("Por favor, informe seu número de WhatsApp."))
            if is_json:
                return JsonResponse({"error": error}, status=400)
            return render(request, template_name, {"error": error})

        phone = normalize_phone(phone_raw)
        if not phone:
            error = str(_("Número de telefone inválido."))
            if is_json:
                return JsonResponse({"error": error}, status=400)
            return render(
                request,
                template_name,
                {"error": error, "phone": phone_raw},
            )

        # Request code
        settings = get_auth_settings()
        result = AuthService.request_code(
            target_value=phone,
            purpose=VerificationCode.Purpose.LOGIN,
            ip_address=get_client_ip(request, settings.TRUSTED_PROXY_DEPTH),
        )

        if not result.success:
            if is_json:
                return JsonResponse({"error": result.error}, status=429)
            return render(
                request,
                template_name,
                {"error": result.error, "phone": phone_raw},
            )

        # Success
        if is_json:
            return JsonResponse({"success": True, "phone": phone})

        # Store phone and next URL in session
        request.session["auth_phone"] = phone
        raw_next = request.POST.get("next") or request.GET.get("next", "")
        if raw_next:
            # Validate before storing to prevent open redirect (H02)
            validated = safe_redirect_url(raw_next, request)
            if validated != get_auth_settings().LOGIN_REDIRECT_URL:
                request.session["doorman_next"] = validated

        return redirect("shopman_auth:code-verify")


class VerificationCodeVerifyView(View):
    """
    Verify a verification code.

    GET /doorman/code/verify
        Renders code_verify.html form

    POST /doorman/code/verify
        Form data: phone=..., code=...
        JSON data: {"phone": "...", "code": "..."}

    On success (form): Redirects to LOGIN_REDIRECT_URL
    On success (JSON): Returns {"success": true, "customer_id": "..."}
    """

    def get_template_name(self):
        """Get template name from settings."""
        settings = get_auth_settings()
        return settings.TEMPLATE_CODE_VERIFY

    def get(self, request):
        phone = request.session.get("auth_phone")
        if not phone:
            return redirect("shopman_auth:code-request")
        return render(request, self.get_template_name(), {"phone": phone})

    def post(self, request):
        template_name = self.get_template_name()
        settings = get_auth_settings()

        # Parse input
        is_json = request.content_type == "application/json"

        if is_json:
            try:
                data = json.loads(request.body)
                phone = data.get("phone", "")
                code = data.get("code", "")
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)
        else:
            phone = request.POST.get("phone") or request.session.get("auth_phone", "")
            code = request.POST.get("code", "")

        # Validate input
        if not phone or not code:
            error = str(_("Telefone e código são obrigatórios."))
            if is_json:
                return JsonResponse({"error": error}, status=400)
            return render(
                request,
                template_name,
                {"error": error, "phone": phone},
            )

        # Normalize phone
        phone = normalize_phone(phone) or phone

        # Verify code
        result = AuthService.verify_for_login(phone, code, request)

        if not result.success:
            if is_json:
                return JsonResponse(
                    {
                        "error": result.error,
                        "attempts_remaining": result.attempts_remaining,
                    },
                    status=400,
                )
            return render(
                request,
                template_name,
                {
                    "error": result.error,
                    "phone": phone,
                    "attempts_remaining": result.attempts_remaining,
                },
            )

        # Create session via access link
        token_result = AccessLinkService.create_token(
            customer=result.customer,
            source=AccessLink.Source.INTERNAL,
        )
        AccessLinkService.exchange(
            token_result.token,
            request,
            preserve_session_keys=settings.PRESERVE_SESSION_KEYS,
        )

        # Get next URL from session before clearing
        next_url = request.session.pop("doorman_next", None)

        # Clear session data
        request.session.pop("auth_phone", None)

        # Success
        if is_json:
            return JsonResponse(
                {
                    "success": True,
                    "customer_id": str(result.customer.uuid),
                }
            )

        # Redirect to next URL or default (H02 - validated)
        redirect_url = safe_redirect_url(next_url, request)
        return redirect(redirect_url)
