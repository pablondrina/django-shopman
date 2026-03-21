"""
Bridge token views.
"""

import json
import logging
import secrets as secrets_mod

from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.utils.translation import gettext_lazy as _
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from ..conf import get_customer_resolver, get_gating_settings
from ..models import BridgeToken
from ..services.auth_bridge import AuthBridgeService
from ..utils import safe_redirect_url

logger = logging.getLogger("shopman.gating.views.bridge")


@method_decorator(csrf_exempt, name="dispatch")
class BridgeTokenCreateView(View):
    """
    Create a bridge token.

    POST /doorman/bridge-tokens

    Request body:
    {
        "customer_id": "uuid",
        "audience": "web_checkout|web_account|web_support|web_general",
        "source": "manychat|api|internal",
        "ttl_minutes": 5,
        "metadata": {}
    }

    Response:
    {
        "url": "https://...",
        "token": "...",
        "expires_at": "..."
    }
    """

    def post(self, request):
        # Authenticate via API key (H05)
        settings = get_gating_settings()
        api_key = settings.BRIDGE_TOKEN_API_KEY
        if api_key:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            x_api_key = request.META.get("HTTP_X_API_KEY", "")
            provided_key = ""
            if auth_header.startswith("Bearer "):
                provided_key = auth_header[7:]
            elif x_api_key:
                provided_key = x_api_key

            if not provided_key or not secrets_mod.compare_digest(provided_key, api_key):
                return JsonResponse({"error": "Unauthorized"}, status=401)

        # Parse JSON
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)

        # Get customer via resolver
        customer_id = data.get("customer_id")
        if not customer_id:
            return JsonResponse({"error": "customer_id required"}, status=400)

        resolver = get_customer_resolver()
        customer = resolver.get_by_uuid(customer_id)
        if not customer:
            return JsonResponse({"error": "Customer not found"}, status=404)

        if not customer.is_active:
            return JsonResponse({"error": "Customer inactive"}, status=400)

        # Create token
        result = AuthBridgeService.create_token(
            customer=customer,
            audience=data.get("audience", BridgeToken.Audience.WEB_GENERAL),
            source=data.get("source", BridgeToken.Source.MANYCHAT),
            ttl_minutes=data.get("ttl_minutes"),
            metadata=data.get("metadata"),
        )

        return JsonResponse(
            {
                "url": result.url,
                "token": result.token,
                "expires_at": result.expires_at,
            }
        )


class BridgeTokenExchangeView(View):
    """
    Exchange a bridge token for a session.

    GET /doorman/bridge/exchange?t=TOKEN

    On success: Redirects to LOGIN_REDIRECT_URL
    On failure: Renders bridge_invalid.html
    """

    def get_template_name(self):
        """Get template name from settings."""
        settings = get_gating_settings()
        return settings.TEMPLATE_BRIDGE_INVALID

    def get(self, request):
        settings = get_gating_settings()
        token = request.GET.get("t")
        if not token:
            return render(
                request,
                self.get_template_name(),
                {"error": str(_("Token não informado."))},
            )

        result = AuthBridgeService.exchange(
            token,
            request,
            preserve_session_keys=settings.PRESERVE_SESSION_KEYS,
        )

        if result.success:
            next_url = safe_redirect_url(request.GET.get("next"), request)
            return redirect(next_url)
        else:
            return render(
                request,
                self.get_template_name(),
                {"error": result.error},
            )
