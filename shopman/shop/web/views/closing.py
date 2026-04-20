"""Fechamento do dia — informe de não vendidos e movimentação D-1 → posição ``ontem``.

GET views consume projections from ``shopman.shop.projections.closing``.
POST actions mutate state, then redirect (PRG pattern).

Fluxo operacional e lacunas: ``docs/guides/day-closing.md``.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from shopman.stockman import Position, Quant
from shopman.stockman.services.movements import StockMovements

from shopman.shop.models import DayClosing
from shopman.shop.projections.closing import build_day_closing

logger = logging.getLogger(__name__)

TEMPLATE = "gestao/fechamento/index.html"
PERMISSION = "shop.perform_closing"


def closing_view(request, admin_site):
    """GET: show closing form. POST: execute closing."""
    if not request.user.has_perm(PERMISSION):
        messages.error(request, "Sem permissão para fechamento do dia.")
        return HttpResponseRedirect(reverse("admin:index"))

    if request.method == "POST":
        return _handle_post(request, admin_site)

    return _render(request, admin_site)


def _handle_post(request, admin_site):
    """Execute day closing: move D-1 eligible, register losses."""
    today = date.today()

    if DayClosing.objects.filter(date=today).exists():
        messages.error(request, "Fechamento de hoje já foi realizado.")
        return HttpResponseRedirect(reverse("admin:shop_closing"))

    closing = build_day_closing()
    snapshot = []

    with transaction.atomic():
        for item in closing.items:
            sku = item.sku
            raw_qty = request.POST.get(f"qty_{sku}", "0").strip()
            try:
                qty_unsold = int(raw_qty)
            except (ValueError, TypeError):
                qty_unsold = 0

            if qty_unsold <= 0:
                snapshot.append({
                    "sku": sku,
                    "qty_remaining": item.qty_available,
                    "qty_d1": 0,
                    "qty_loss": 0,
                })
                continue

            qty_unsold = min(qty_unsold, item.qty_available)
            qty_d1 = 0
            qty_loss = 0

            if item.classification == "d1":
                ontem_pos = Position.objects.filter(ref="ontem").first()
                if ontem_pos:
                    _issue_from_saleable(sku, qty_unsold, f"fechamento:{today}")
                    StockMovements.receive(
                        quantity=Decimal(qty_unsold),
                        sku=sku,
                        position=ontem_pos,
                        batch="D-1",
                        reason=f"d1:{today}",
                        user=request.user,
                    )
                    qty_d1 = qty_unsold
            elif item.classification == "loss":
                _issue_from_saleable(sku, qty_unsold, f"perda:{today}")
                qty_loss = qty_unsold

            snapshot.append({
                "sku": sku,
                "qty_remaining": item.qty_available - qty_unsold,
                "qty_d1": qty_d1,
                "qty_loss": qty_loss,
            })

        DayClosing.objects.create(
            date=today,
            closed_by=request.user,
            data=snapshot,
        )

    messages.success(request, f"Fechamento do dia {today} realizado com sucesso.")
    return HttpResponseRedirect(reverse("admin:shop_closing"))


def _issue_from_saleable(sku, quantity, reason):
    """Issue stock from saleable positions (excluding 'ontem')."""
    quants = (
        Quant.objects.filter(
            sku=sku,
            position__is_saleable=True,
            _quantity__gt=0,
        )
        .exclude(position__ref="ontem")
        .select_for_update()
        .order_by("pk")
    )
    remaining = Decimal(quantity)
    for quant in quants:
        if remaining <= 0:
            break
        take = min(remaining, quant._quantity)
        StockMovements.issue(quantity=take, quant=quant, reason=reason)
        remaining -= take


def _render(request, admin_site):
    """Render the closing page using projection."""
    closing = build_day_closing()

    context = {
        **admin_site.each_context(request),
        "title": "Fechamento do Dia",
        "closing": closing,
        "items": closing.items,
        "today": date.today(),
        "existing_closing": closing.already_closed,
        "has_old_d1": closing.has_old_d1,
    }
    return TemplateResponse(request, TEMPLATE, context)
