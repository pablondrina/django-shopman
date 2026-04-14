"""
Bridge token view — validates ?t=<token> and binds session.

Bridge token from WhatsApp/Instagram — first-class entry paths.
creates authenticated session and sets origin_channel.
"""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views import View

logger = logging.getLogger("shopman.shop.web.bridge")

# Maps AccessLink.source → origin_channel value
SOURCE_TO_ORIGIN = {
    "manychat": "whatsapp",  # Default Manychat → WhatsApp; overridden by metadata
    "api": "web",
    "internal": "web",
}


class BridgeTokenView(View):
    """
    Handles ?t=<token> on any storefront URL.

    Validates the bridge token (AccessLink), authenticates the user,
    sets origin_channel on the Django session, and redirects to the
    target URL (default: /menu/).

    origin_channel is later propagated to Orderman Session and Order
    for notification routing.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        token_str = request.GET.get("t", "").strip()
        if not token_str:
            return redirect("storefront:menu")

        # Exchange token for session
        result = self._exchange_token(token_str, request)

        if not result.success:
            logger.warning(
                "Bridge token invalid: %s (error=%s)",
                token_str[:8],
                result.error,
            )
            # Don't block access — redirect to menu as anonymous
            return redirect("storefront:menu")

        # Determine origin_channel from token metadata + source
        origin = self._resolve_origin(result)
        request.session["origin_channel"] = origin

        logger.info(
            "Bridge token exchanged: customer=%s origin=%s",
            result.customer.uuid if result.customer else "?",
            origin,
        )

        # Redirect to intended destination (strip token from URL)
        next_url = request.GET.get("next", "/menu/")
        return redirect(next_url)

    @staticmethod
    def _exchange_token(token_str: str, request: HttpRequest):
        """Exchange AccessLink token for Django session."""
        from shopman.doorman.services.access_link import AccessLinkService

        return AccessLinkService.exchange(
            token_str=token_str,
            request=request,
            preserve_session_keys=["cart_session_key"],
        )

    @staticmethod
    def _resolve_origin(result) -> str:
        """Determine origin_channel from exchange result."""
        # Try metadata first (set by Manychat webhook with explicit channel)
        if result.customer:
            # The token's metadata may contain explicit origin
            pass

        # Default mapping from source
        # For Manychat, check if it's Instagram or WhatsApp
        source = "web"
        try:
            from shopman.doorman.models import AccessLink

            token = AccessLink.objects.filter(
                customer_id=result.customer.uuid,
            ).order_by("-created_at").first()
            if token:
                source = token.source
                # Check metadata for explicit channel
                meta = token.metadata or {}
                if meta.get("channel") == "instagram":
                    return "instagram"
                if meta.get("channel") == "whatsapp":
                    return "whatsapp"
        except Exception:
            logger.exception("bridge_resolve_origin_failed")

        return SOURCE_TO_ORIGIN.get(source, "web")
