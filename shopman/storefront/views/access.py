"""
AccessLink entry view — validates ?t=<token> and binds session.

Pre-authenticated entry from WhatsApp/Instagram notifications.
Exchanges the AccessLink token, creates an authenticated session,
sets origin_channel, and redirects to the intended destination.
"""

from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views import View

from shopman.shop.services import access as access_service

logger = logging.getLogger("shopman.storefront.views.access")


class AccessLinkEntryView(View):
    """
    Handles ?t=<token> on any storefront URL.

    Validates the AccessLink token, authenticates the user,
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
                "AccessLink invalid: %s (error=%s)",
                token_str[:8],
                result.error,
            )
            # Don't block access — redirect to menu as anonymous
            return redirect("storefront:menu")

        # Determine origin_channel from token metadata + source
        origin = self._resolve_origin(result)
        request.session["origin_channel"] = origin

        logger.info(
            "AccessLink exchanged: customer=%s origin=%s",
            result.customer.uuid if result.customer else "?",
            origin,
        )

        # Redirect to intended destination (strip token from URL)
        next_url = request.GET.get("next", "/menu/")
        return redirect(next_url)

    @staticmethod
    def _exchange_token(token_str: str, request: HttpRequest):
        """Exchange AccessLink token for Django session."""
        return access_service.exchange_token(token_str, request)

    @staticmethod
    def _resolve_origin(result) -> str:
        """Determine origin_channel from exchange result."""
        return access_service.resolve_origin(result)
