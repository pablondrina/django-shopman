"""Custom error views for the backstage (gestor) interface."""
from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render


def custom_404(request: HttpRequest, exception=None) -> HttpResponse:
    return render(request, "gestor/404.html", status=404)
