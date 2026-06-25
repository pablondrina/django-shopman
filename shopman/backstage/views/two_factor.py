"""Admin two-factor (TOTP) verification interstitial.

Shown by ``AdminTwoFactorMiddleware`` when ``SHOPMAN_ADMIN_REQUIRE_2FA`` is on and
an authenticated staff user is not yet OTP-verified. The user enters a TOTP code
from their authenticator; on success the session is marked verified and they
continue to ``next`` (admin only). Enrollment is out-of-band (``setup_admin_totp``).
"""

from __future__ import annotations

from django.http import HttpResponseRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods
from django_otp import login as otp_login
from django_otp.plugins.otp_totp.models import TOTPDevice


def _safe_next(request) -> str:
    nxt = request.POST.get("next") or request.GET.get("next") or ""
    # Only allow local admin redirects (no open redirect, no leaving /admin/).
    if nxt.startswith("/admin/"):
        return nxt
    return reverse("admin:index")


@require_http_methods(["GET", "POST"])
def admin_2fa_verify(request):
    if not (request.user.is_authenticated and request.user.is_staff):
        return redirect(f"{reverse('admin:login')}?next={request.get_full_path()}")

    next_url = _safe_next(request)
    if request.user.is_verified():
        return HttpResponseRedirect(next_url)

    device = TOTPDevice.objects.filter(user=request.user, confirmed=True).first()
    error = ""
    if request.method == "POST" and device is not None:
        token = (request.POST.get("token") or "").strip().replace(" ", "")
        if token and device.verify_token(token):
            otp_login(request, device)
            return HttpResponseRedirect(next_url)
        error = "Código inválido. Confira o app autenticador e tente de novo."

    return render(
        request,
        "two_factor/verify.html",
        {
            "has_device": device is not None,
            "error": error,
            "next": next_url,
            "username": request.user.get_username(),
        },
    )
