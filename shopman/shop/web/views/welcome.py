"""Welcome step — captures customer's display name on first login.

Shown to any authenticated customer whose `first_name` is empty. Pre-fills
the input with a sanitized version of whatever name we already have (often
from ManyChat) so the customer only has to confirm.
"""
from __future__ import annotations

import re

from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import ensure_csrf_cookie

from shopman.guestman.services import customer as customer_service


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002600-\U000026FF"
    "\U00002700-\U000027BF"
    "\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)
_WHITESPACE_RE = re.compile(r"\s+")
_SUSPECT_CHARS = ("&", "+", "|", "/")


def clean_display_name(raw: str) -> str:
    """Leve: tira emojis e normaliza espaços. Não tenta adivinhar splits."""
    if not raw:
        return ""
    cleaned = _EMOJI_RE.sub("", raw)
    cleaned = _WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def needs_confirmation(raw: str) -> bool:
    """True when the stored name is empty or looks auto-imported (ManyChat quirks)."""
    if not (raw or "").strip():
        return True
    if _EMOJI_RE.search(raw):
        return True
    if any(ch in raw for ch in _SUSPECT_CHARS):
        return True
    return False


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

        cust = customer_service.get_by_uuid(str(customer_info.uuid))
        raw = f"{cust.first_name} {cust.last_name}".strip() if cust else ""
        suggested = clean_display_name(raw)

        return render(request, self.template_name, {
            "suggested_name": suggested,
            "next_url": self._safe_next(request),
        })

    def post(self, request: HttpRequest) -> HttpResponse:
        customer_info = getattr(request, "customer", None)
        if customer_info is None:
            return redirect("storefront:login")

        name = clean_display_name(request.POST.get("name", ""))
        if not name:
            return render(request, self.template_name, {
                "suggested_name": "",
                "next_url": self._safe_next(request),
                "error": "Precisamos de um nome para te chamar.",
            })

        cust = customer_service.get_by_uuid(str(customer_info.uuid))
        if cust is None:
            return redirect("storefront:login")

        parts = name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""
        customer_service.update(cust.ref, first_name=first_name, last_name=last_name)

        # Bust the cached AuthCustomerInfo on request.user so navbar picks up the new name
        if hasattr(request.user, "_shopman_customer_info"):
            delattr(request.user, "_shopman_customer_info")

        return redirect(self._safe_next(request))

    def _resume(self, request: HttpRequest) -> HttpResponse:
        return redirect(self._safe_next(request))

    @staticmethod
    def _safe_next(request: HttpRequest) -> str:
        nxt = request.GET.get("next") or request.POST.get("next") or "/"
        # Only accept relative paths to avoid open redirect.
        if not nxt.startswith("/") or nxt.startswith("//"):
            return "/"
        return nxt
