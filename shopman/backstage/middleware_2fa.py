"""Admin two-factor (TOTP) gate.

When ``SHOPMAN_ADMIN_REQUIRE_2FA`` is enabled, any authenticated staff user
reaching ``/admin/`` must be OTP-verified (a confirmed TOTP device + a verified
session via the verify view). Off by default so it never locks anyone out before
enrollment; enable only after each admin has a device (``setup_admin_totp``).

Relies on ``django_otp.middleware.OTPMiddleware`` (which sets
``request.user.is_verified()``) running earlier in the stack.
"""

from __future__ import annotations

from django.conf import settings
from django.shortcuts import redirect
from django.urls import NoReverseMatch, reverse
from django.utils.http import urlencode


class AdminTwoFactorMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self._needs_verification(request):
            try:
                verify_url = reverse("admin_2fa_verify")
            except NoReverseMatch:
                return self.get_response(request)
            return redirect(f"{verify_url}?{urlencode({'next': request.get_full_path()})}")
        return self.get_response(request)

    @staticmethod
    def _needs_verification(request) -> bool:
        if not getattr(settings, "SHOPMAN_ADMIN_REQUIRE_2FA", False):
            return False
        path = request.path
        if not path.startswith("/admin/"):
            return False
        # Let admin's own auth handle login/logout; never gate the verify view itself
        # (would loop). Compare against the resolved verify URL + the admin auth paths.
        try:
            verify_url = reverse("admin_2fa_verify")
        except NoReverseMatch:
            return False
        if path == verify_url or path.startswith("/admin/login") or path.startswith("/admin/logout"):
            return False
        user = getattr(request, "user", None)
        if not (user and user.is_authenticated and user.is_staff):
            return False  # unauthenticated → admin login flow handles it
        # is_verified() is added by OTPMiddleware; True once a TOTP token was accepted.
        return not user.is_verified()
