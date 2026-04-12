"""Shopman middleware — onboarding redirect + channel param capture."""

from __future__ import annotations

from django.shortcuts import redirect

from .models import Shop

# Valid origin_channel values that can be set via ?channel= URL parameter
VALID_CHANNEL_PARAMS = {"whatsapp", "instagram", "web"}


class ChannelParamMiddleware:
    """Capture ?channel=whatsapp from URL and store in Django session.

    When a customer visits any storefront URL with ?channel=whatsapp,
    the value is persisted as origin_channel in the Django session.
    This is later propagated to Orderman Session.data for notification routing.

    Only sets once per session (doesn't overwrite bridge-token origin).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        channel_param = request.GET.get("channel", "").strip().lower()
        if channel_param and channel_param in VALID_CHANNEL_PARAMS:
            # Only set if not already set by bridge token
            if "origin_channel" not in request.session:
                request.session["origin_channel"] = channel_param

        return self.get_response(request)


class OnboardingMiddleware:
    """Redirect staff to /gestao/setup/ if no Shop exists.

    Uses Shop.load() (cached singleton) so this costs zero DB queries
    in normal operation. Only falls through to .exists() if cache miss
    returns None AND objects.first() returns None.
    """

    SETUP_PATH = "/gestao/setup/"
    GUARDED_PREFIXES = ("/admin/", "/gestao/")
    # Static files and API should never trigger redirect
    SKIP_PREFIXES = ("/static/", "/media/", "/api/", "/favicon")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        # Fast-path: skip non-guarded paths
        if not any(path.startswith(p) for p in self.GUARDED_PREFIXES):
            return self.get_response(request)

        # Skip static/media/api
        if any(path.startswith(p) for p in self.SKIP_PREFIXES):
            return self.get_response(request)

        # Don't redirect the setup page itself
        if path.startswith(self.SETUP_PATH):
            return self.get_response(request)

        # Only redirect authenticated staff
        if not getattr(request.user, "is_staff", False):
            return self.get_response(request)

        # Shop.load() uses cache — zero DB queries on subsequent requests
        if Shop.load() is None:
            return redirect(self.SETUP_PATH)

        return self.get_response(request)
