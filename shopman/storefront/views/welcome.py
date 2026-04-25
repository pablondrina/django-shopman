"""Welcome step — captures customer's display name on first login.

Shown to any authenticated customer whose `first_name` is empty. Pre-fills
the input with a sanitized version of whatever name we already have (often
from ManyChat) so the customer only has to confirm.
"""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from ..intents.auth import clean_display_name, interpret_welcome, needs_confirmation
from ..services import auth as auth_service


@method_decorator(ensure_csrf_cookie, name="dispatch")
class WelcomeView(View):
    """GET: show welcome form. POST: save name and redirect to ?next= or home."""

    template_name = "storefront/welcome.html"

    def get(self, request: HttpRequest) -> HttpResponse:
        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return redirect("storefront:login")

        # If the customer already has a clean, confirmed name, they don't need this step.
        if not needs_confirmation(customer_info.name or ""):
            return self._resume(request)

        cust = auth_service.customer_by_uuid(str(customer_info.uuid))
        raw = f"{cust.first_name} {cust.last_name}".strip() if cust else ""
        suggested = clean_display_name(raw)

        return render(request, self.template_name, {
            "suggested_name": suggested,
            "next_url": self._safe_next(request),
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        result = interpret_welcome(request)

        if result.intent is None:
            if "auth" in result.errors:
                return redirect("storefront:login")
            return render(request, self.template_name, {
                "suggested_name": "",
                "next_url": result.form_data.get("next", "/"),
                "error": result.errors.get("name", ""),
            })

        intent = result.intent

        cust = auth_service.customer_by_uuid(intent.customer_uuid)
        if cust is None:
            return redirect("storefront:login")

        parts = intent.name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        auth_service.update_customer_name(cust.ref, first_name=first_name, last_name=last_name)

        # Bust the cached AuthCustomerInfo on request.user so navbar picks up the new name
        if hasattr(request.user, "_shopman_customer_info"):
            delattr(request.user, "_shopman_customer_info")

        return redirect(intent.next_url)

    def _resume(self, request: HttpRequest) -> HttpResponse:
        return redirect(self._safe_next(request))

    @staticmethod
    def _safe_next(request: HttpRequest) -> str:
        nxt = request.GET.get("next") or request.POST.get("next") or "/"
        # Only accept relative paths to avoid open redirect.
        if not nxt.startswith("/") or nxt.startswith("//"):
            return "/"
        return nxt
