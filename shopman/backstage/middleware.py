"""Backstage middleware — onboarding redirect for operator surfaces."""

from __future__ import annotations

from django.shortcuts import redirect

from shopman.shop.models import Shop


class OnboardingMiddleware:
    """Redirect staff to /gestao/setup/ if no Shop exists.

    Uses Shop.load() (cached singleton) so this costs zero DB queries
    in normal operation. Only falls through to .exists() if cache miss
    returns None AND objects.first() returns None.
    """

    SETUP_PATH = "/gestao/setup/"
    GUARDED_PREFIXES = ("/admin/", "/gestao/")
    SKIP_PREFIXES = ("/static/", "/media/", "/api/", "/favicon")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path

        if not any(path.startswith(p) for p in self.GUARDED_PREFIXES):
            return self.get_response(request)

        if any(path.startswith(p) for p in self.SKIP_PREFIXES):
            return self.get_response(request)

        if path.startswith(self.SETUP_PATH):
            return self.get_response(request)

        if not getattr(request.user, "is_staff", False):
            return self.get_response(request)

        if Shop.load() is None:
            return redirect(self.SETUP_PATH)

        return self.get_response(request)
