"""
Access link request views — email-based one-click login.
"""

import json
import logging

from django.http import JsonResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views import View

from ..conf import get_doorman_settings
from ..error_codes import ErrorCode
from ..services.access_link import AccessLinkService
from ..utils import get_client_ip

_RATE_LIMIT_CODES = frozenset({ErrorCode.EMAIL_RATE_LIMIT, ErrorCode.IP_RATE_LIMIT})

logger = logging.getLogger("shopman.doorman.views.access_link")


class AccessLinkRequestView(View):
    """
    Request an access link via email.

    GET /doorman/access-link/
        Renders access_link_request.html form

    POST /doorman/access-link/
        Form data: email=...
        JSON data: {"email": "..."}

    On success (form): Re-renders with "sent" flag
    On success (JSON): Returns {"success": true}
    """

    def get_template_name(self):
        settings = get_doorman_settings()
        return settings.TEMPLATE_ACCESS_LINK_REQUEST

    def get(self, request):
        if not get_doorman_settings().ACCESS_LINK_ENABLED:
            return render(
                request,
                self.get_template_name(),
                {"error": str(_("Login via email is not available."))},
            )
        context = {"next": request.GET.get("next", "")}
        return render(request, self.get_template_name(), context)

    def post(self, request):
        template_name = self.get_template_name()

        if not get_doorman_settings().ACCESS_LINK_ENABLED:
            return JsonResponse(
                {"error": "Access links are disabled."}, status=400
            )

        # Parse input
        is_json = request.content_type == "application/json"

        if is_json:
            try:
                data = json.loads(request.body)
                email = data.get("email", "").strip().lower()
            except json.JSONDecodeError:
                return JsonResponse({"error": "Invalid JSON"}, status=400)
        else:
            email = request.POST.get("email", "").strip().lower()

        # Validate
        if not email or "@" not in email:
            error = str(_("Please enter a valid email address."))
            if is_json:
                return JsonResponse({"error": error}, status=400)
            return render(request, template_name, {"error": error, "email": email})

        # Send access link
        settings = get_doorman_settings()
        ip_address = get_client_ip(request, settings.TRUSTED_PROXY_DEPTH)
        result = AccessLinkService.send_access_link(email, ip_address=ip_address)

        if not result.success:
            http_status = 429 if result.error_code in _RATE_LIMIT_CODES else 400
            if is_json:
                return JsonResponse({"error": result.error}, status=http_status)
            return render(
                request,
                template_name,
                {"error": result.error, "email": email},
            )

        # Success
        if is_json:
            return JsonResponse({"success": True})

        return render(request, template_name, {"sent": True, "email": email})
