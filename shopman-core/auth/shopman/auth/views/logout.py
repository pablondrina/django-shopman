"""
Logout view.

POST-only to prevent CSRF via GET links. Clears Django session
and device trust cookie.
"""

from __future__ import annotations

import logging

from django.contrib.auth import logout
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.views import View

from ..conf import auth_settings
from ..services.device_trust import DeviceTrustService

logger = logging.getLogger("shopman.auth.views.logout")


class LogoutView(View):
    """POST-only logout: clears session + device trust cookie."""

    def post(self, request):
        # Redirect to ?next= if provided, otherwise default
        from ..utils import safe_redirect_url

        next_url = request.POST.get("next") or request.GET.get("next")
        redirect_url = safe_redirect_url(next_url, request) if next_url else auth_settings.LOGOUT_REDIRECT_URL
        response = HttpResponseRedirect(redirect_url)

        # Clear device trust cookie
        DeviceTrustService.revoke_device(request, response)

        # Django logout (flushes session)
        logout(request)

        logger.info("User logged out")

        return response

    def get(self, request):
        return HttpResponseNotAllowed(["POST"])
