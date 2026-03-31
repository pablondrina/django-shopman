"""Home view — institutional landing page."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views import View


class HomeView(View):
    """Institutional home page — brand vitrine."""

    def get(self, request: HttpRequest) -> HttpResponse:
        return render(request, "storefront/home.html")
