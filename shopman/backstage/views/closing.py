"""Fechamento do dia — informe de não vendidos e movimentação D-1 → posição ``ontem``.

GET views consume projections from ``shopman.shop.projections.closing``.
POST actions mutate state, then redirect (PRG pattern).

Fluxo operacional e lacunas: ``docs/guides/day-closing.md``.
"""

from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse

from shopman.backstage.projections.closing import build_day_closing
from shopman.backstage.services.closing import perform_day_closing

TEMPLATE = "gestor/fechamento/index.html"
PERMISSION = "backstage.perform_closing"


def closing_view(request):
    """GET: show closing form. POST: execute closing."""
    denied = _staff_required(request)
    if denied:
        return denied

    if not request.user.has_perm(PERMISSION):
        messages.error(request, "Sem permissão para fechamento do dia.")
        return HttpResponseRedirect(reverse("admin:index"))

    if request.method == "POST":
        return _handle_post(request)

    return _render(request)


def _staff_required(request):
    if not request.user.is_authenticated or not request.user.is_staff:
        return redirect(f"/admin/login/?next={request.path}")
    return None


def _handle_post(request):
    """Execute day closing: move D-1 eligible, register losses."""
    closing = build_day_closing()
    try:
        closing_date = perform_day_closing(
            user=request.user,
            items=closing.items,
            quantities_by_sku={
                item.sku: request.POST.get(f"qty_{item.sku}", "0")
                for item in closing.items
            },
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return HttpResponseRedirect(reverse("backstage:day_closing"))

    messages.success(request, f"Fechamento do dia {closing_date} realizado com sucesso.")
    return HttpResponseRedirect(reverse("backstage:day_closing"))


def _render(request):
    """Render the closing page using projection."""
    closing = build_day_closing()

    context = {
        "title": "Fechamento do Dia",
        "closing": closing,
        "items": closing.items,
        "today": date.today(),
        "existing_closing": closing.already_closed,
        "has_old_d1": closing.has_old_d1,
    }
    return TemplateResponse(request, TEMPLATE, context)
