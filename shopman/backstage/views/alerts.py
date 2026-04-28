"""Operator alert fragments shared by backstage surfaces."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from shopman.backstage.operator.context import build_operator_context
from shopman.backstage.services import alerts as alert_service


def _staff_required(request: HttpRequest):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    return None


@require_GET
def alerts_badge(request: HttpRequest) -> HttpResponse:
    denied = _staff_required(request)
    if denied:
        return denied

    return render(
        request,
        "gestor/partials/alerts_badge.html",
        {"operator": build_operator_context(request)},
    )


@require_GET
def alerts_panel(request: HttpRequest) -> HttpResponse:
    denied = _staff_required(request)
    if denied:
        return denied

    return _render_alerts_panel(request)


def _render_alerts_panel(request: HttpRequest) -> HttpResponse:
    return render(
        request,
        "gestor/partials/alerts_panel.html",
        {"alerts": alert_service.list_active_alerts(limit=12)},
    )


@require_POST
def alert_ack(request: HttpRequest, pk: int) -> HttpResponse:
    denied = _staff_required(request)
    if denied:
        return HttpResponseForbidden("Você não tem permissão para esta ação.")

    alert_service.ack_alert(pk)
    if request.headers.get("HX-Request"):
        return _render_alerts_panel(request)
    return HttpResponse("")
