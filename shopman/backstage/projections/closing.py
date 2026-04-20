"""DayClosingProjection — read models for the day closing page (Fase 4).

Translates saleable stock, product classifications, and closing history into
immutable projections. Replaces the inline ``_build_items`` / ``_has_old_d1_stock``
logic from ``shopman.shop.web.views.closing``.

Never imports from ``shopman.shop.web.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta

from django.db.models import Sum
from shopman.offerman.models import Product
from shopman.stockman import Move, Position, Quant

from shopman.backstage.models import DayClosing

logger = logging.getLogger(__name__)


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ClosingItemProjection:
    """A single SKU row in the day closing form."""

    sku: str
    name: str
    qty_available: int
    classification: str  # "d1", "loss", "neutral"
    badge_label: str  # "D-1", "Perda", "Neutro"
    badge_css: str  # Tailwind classes for badge


@dataclass(frozen=True)
class ClosingSnapshotItemProjection:
    """A single SKU row from a completed closing snapshot."""

    sku: str
    qty_remaining: int
    qty_d1: int
    qty_loss: int


@dataclass(frozen=True)
class DayClosingProjection:
    """Top-level read model for the day closing page."""

    today: str  # ISO date
    today_display: str  # "16/04/2026"
    items: tuple[ClosingItemProjection, ...]
    has_items: bool
    already_closed: bool
    existing_closing_display: str  # "" if not closed, "Fechado por X às HH:MM"
    has_old_d1: bool  # D-1 stock older than 1 day in "ontem" position
    total_available: int


# ── Builder ────────────────────────────────────────────────────────────


def build_day_closing() -> DayClosingProjection:
    """Build the day closing projection for today."""
    today = date.today()
    existing = DayClosing.objects.filter(date=today).first()

    items = _build_items()
    total_available = sum(it.qty_available for it in items)

    closing_display = ""
    if existing:
        by = existing.closed_by.get_username() if existing.closed_by else "?"
        at = existing.closed_at.strftime("%H:%M") if existing.closed_at else ""
        closing_display = f"Fechado por {by} às {at}"

    return DayClosingProjection(
        today=today.isoformat(),
        today_display=today.strftime("%d/%m/%Y"),
        items=tuple(items),
        has_items=bool(items),
        already_closed=existing is not None,
        existing_closing_display=closing_display,
        has_old_d1=_has_old_d1_stock(),
        total_available=total_available,
    )


# ── Internals ──────────────────────────────────────────────────────────


def _build_items() -> list[ClosingItemProjection]:
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

    items: list[ClosingItemProjection] = []
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
            badge_css = "bg-warning/80 text-warning-foreground"
        elif shelf_life == 0:
            classification = "loss"
            badge_label = "Perda"
            badge_css = "bg-danger/80 text-danger-foreground"
        else:
            classification = "neutral"
            badge_label = "Neutro"
            badge_css = "bg-muted text-muted-foreground"

        items.append(
            ClosingItemProjection(
                sku=sku,
                name=name,
                qty_available=int(qty),
                classification=classification,
                badge_label=badge_label,
                badge_css=badge_css,
            )
        )

    return items


def _has_old_d1_stock() -> bool:
    """Check if there's D-1 stock older than 1 day in position 'ontem'."""
    ontem_pos = Position.objects.filter(ref="ontem").first()
    if not ontem_pos:
        return False

    old_quants = Quant.objects.filter(position=ontem_pos, _quantity__gt=0)
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
