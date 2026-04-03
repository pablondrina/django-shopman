"""Home view — institutional landing page."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.clickjacking import xframe_options_sameorigin


@method_decorator(xframe_options_sameorigin, name="dispatch")
class HomeView(View):
    """Institutional home page — brand vitrine.

    SAMEORIGIN permite embed no admin (WP-S4 preview iframe), sem abrir a página a clickjacking de terceiros.
    """

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/home.html")
