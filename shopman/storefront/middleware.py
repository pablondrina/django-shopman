"""Storefront middleware — channel param capture.

Headless: the customer surface is the Nuxt store. The welcome gate (name
capture for first-time customers) is handled by the store; the Django side only
captures the origin channel for notification routing.
"""

from __future__ import annotations

# Valid origin_channel values that can be set via ?channel= URL parameter
VALID_CHANNEL_PARAMS = {"whatsapp", "instagram", "web"}


class ChannelParamMiddleware:
    """Capture ?channel=whatsapp from URL and store in Django session.

    When a request carries ?channel=whatsapp, the value is persisted as
    origin_channel in the Django session. This is later propagated to Orderman
    Session.data for notification routing.

    Only sets once per session (doesn't overwrite access-link origin).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        channel_param = request.GET.get("channel", "").strip().lower()
        if channel_param and channel_param in VALID_CHANNEL_PARAMS:
            if "origin_channel" not in request.session:
                request.session["origin_channel"] = channel_param

        return self.get_response(request)
