"""Fechamento do dia — informe de não vendidos e movimentação D-1 → posição ``ontem``.

Fluxo operacional e lacunas: ``docs/guides/day-closing.md``.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponseRedirect
from django.template.response import TemplateResponse
from django.urls import reverse
from shopman.offerman.models import Product
from shopman.stockman import Move, Position, Quant
from shopman.stockman.services.movements import StockMovements

from shopman.shop.models import DayClosing

logger = logging.getLogger(__name__)

TEMPLATE = "admin/shop/closing.html"
PERMISSION = "shop.add_dayclosing"


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

    items = _build_items()
    snapshot = []

    with transaction.atomic():
        for item in items:
            sku = item["sku"]
            raw_qty = request.POST.get(f"qty_{sku}", "0").strip()
            try:
                qty_unsold = int(raw_qty)
            except (ValueError, TypeError):
                qty_unsold = 0

            if qty_unsold <= 0:
                snapshot.append({
                    "sku": sku,
                    "qty_remaining": int(item["qty_available"]),
                    "qty_d1": 0,
                    "qty_loss": 0,
                })
                continue

            # Cap at available
            qty_unsold = min(qty_unsold, int(item["qty_available"]))
            qty_d1 = 0
            qty_loss = 0

            if item["classification"] == "d1":
                # Move to position "ontem"
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
            elif item["classification"] == "loss":
                # Register loss
                _issue_from_saleable(sku, qty_unsold, f"perda:{today}")
                qty_loss = qty_unsold
            # "neutral" → skip (non-perishable stays in stock)

            snapshot.append({
                "sku": sku,
                "qty_remaining": int(item["qty_available"]) - qty_unsold,
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
    """Render the closing page."""
    today = date.today()
    existing_closing = DayClosing.objects.filter(date=today).first()
    items = _build_items()

    # Check for old D-1 stock (moves > 1 day old in "ontem")
    has_old_d1 = _has_old_d1_stock()

    context = {
        **admin_site.each_context(request),
        "title": "Fechamento do Dia",
        "items": items,
        "today": today,
        "existing_closing": existing_closing,
        "has_old_d1": has_old_d1,
    }
    return TemplateResponse(request, TEMPLATE, context)


def _build_items():
    """Build list of SKUs with saleable stock for closing."""
    quants = (
        Quant.objects.filter(
            position__is_saleable=True,
            _quantity__gt=0,
        )
        .exclude(position__ref="ontem")
        .values("sku")
        .annotate(total_qty=Sum("_quantity"))
        .order_by("sku")
    )

    items = []
    for row in quants:
        sku = row["sku"]
        qty = row["total_qty"]

        try:
            product = Product.objects.get(sku=sku)
        except Product.DoesNotExist:
            product = None

        name = product.name if product else sku
        shelf_life = product.shelf_life_days if product else None
        allows_d1 = (
            product.metadata.get("allows_next_day_sale", False)
            if product
            else False
        )

        if allows_d1:
            classification = "d1"
            badge_label = "D-1"
            badge_css = "bg-amber-500"
        elif shelf_life == 0:
            classification = "loss"
            badge_label = "Perda"
            badge_css = "bg-red-500"
        else:
            classification = "neutral"
            badge_label = "Neutro"
            badge_css = "bg-gray-400"

        items.append({
            "sku": sku,
            "name": name,
            "qty_available": qty,
            "classification": classification,
            "badge_label": badge_label,
            "badge_css": badge_css,
        })

    return items


def _has_old_d1_stock():
    """Check if there's D-1 stock older than 1 day in position 'ontem'."""
    ontem_pos = Position.objects.filter(ref="ontem").first()
    if not ontem_pos:
        return False

    old_quants = Quant.objects.filter(
        position=ontem_pos,
        _quantity__gt=0,
    )
    if not old_quants.exists():
        return False

    threshold = date.today() - timedelta(days=1)
    for quant in old_quants:
        last_move = (
            Move.objects.filter(quant=quant, reason__startswith="d1:")
            .order_by("-timestamp")
            .first()
        )
        if last_move and last_move.timestamp.date() < threshold:
            return True

    return False
