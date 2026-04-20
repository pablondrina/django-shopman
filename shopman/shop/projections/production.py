"""ProductionBoardProjection — read models for the production board (Fase 4).

Translates Craftsman work orders, queue items, and summary into immutable
projections for the operator production page. Replaces the inline context
building from ``shopman.shop.web.views.production``.

Never imports from ``shopman.shop.web.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, WorkOrder
from shopman.stockman import Position

logger = logging.getLogger(__name__)


# ── Status labels & colors ─────────────────────────────────────────────

WO_STATUS_LABELS: dict[str, str] = {
    "planned": "Planejado",
    "started": "Iniciado",
    "finished": "Concluído",
    "void": "Estornado",
}

WO_STATUS_COLORS: dict[str, str] = {
    "planned": "bg-info/10 text-info border border-info/20",
    "started": "bg-warning/10 text-warning border border-warning/20",
    "finished": "bg-success/10 text-success border border-success/20",
    "void": "bg-danger/10 text-danger border border-danger/20",
}


# ── Projections ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class WorkOrderCardProjection:
    """A single work order card on the production board."""

    pk: int
    ref: str
    recipe_ref: str
    recipe_name: str
    output_ref: str
    status: str
    status_label: str
    status_color: str
    planned_qty: str  # pre-formatted, e.g. "100"
    started_qty: str  # "" if not started
    finished_qty: str  # "" if not finished
    yield_rate: str  # "92%" or ""
    loss: str  # "8" or ""
    operator_ref: str
    position_ref: str
    target_date_display: str
    started_at_display: str
    created_at_display: str
    can_void: bool


@dataclass(frozen=True)
class ProductionCountsProjection:
    """Aggregate counts for the production board header."""

    total: int
    planned: int
    started: int
    finished: int
    void: int
    planned_qty: str  # total planned quantity
    started_qty: str
    finished_qty: str
    loss_qty: str


@dataclass(frozen=True)
class RecipeOptionProjection:
    """A recipe available for quick production form."""

    pk: int
    ref: str
    name: str  # output_ref or recipe ref display


@dataclass(frozen=True)
class PositionOptionProjection:
    """A stock position available for production form."""

    pk: int
    ref: str
    name: str
    is_default: bool


@dataclass(frozen=True)
class ProductionBoardProjection:
    """Top-level read model for the production board."""

    selected_date: str  # ISO date
    selected_date_display: str  # "16/04/2026"
    selected_position_ref: str
    selected_operator_ref: str
    work_orders: tuple[WorkOrderCardProjection, ...]
    counts: ProductionCountsProjection
    planned_queue: tuple[WorkOrderCardProjection, ...]
    started_queue: tuple[WorkOrderCardProjection, ...]
    recipes: tuple[RecipeOptionProjection, ...]
    positions: tuple[PositionOptionProjection, ...]
    default_position_pk: int | None


# ── Builders ───────────────────────────────────────────────────────────


def build_production_board(
    *,
    selected_date: date | None = None,
    position_ref: str = "",
    operator_ref: str = "",
) -> ProductionBoardProjection:
    """Build the production board projection."""
    selected_date = selected_date or date.today()

    # Fetch work orders for the selected date
    wos_qs = (
        WorkOrder.objects
        .filter(target_date=selected_date)
        .select_related("recipe")
        .order_by("-created_at")
    )
    if position_ref:
        wos_qs = wos_qs.filter(position_ref=position_ref)
    if operator_ref:
        wos_qs = wos_qs.filter(operator_ref=operator_ref)

    wo_cards = tuple(_build_wo_card(wo) for wo in wos_qs)

    # Craft summary via service
    summary = craft.summary(
        date=selected_date,
        position_ref=position_ref or None,
        operator_ref=operator_ref or None,
    )

    # Queue items (planned + started)
    queue_items = craft.queue(
        date=selected_date,
        position_ref=position_ref or None,
        operator_ref=operator_ref or None,
    )

    planned_queue = tuple(
        _build_wo_card(
            WorkOrder.objects.select_related("recipe").get(ref=item.ref),
        )
        for item in queue_items
        if item.status == WorkOrder.Status.PLANNED
    )
    started_queue = tuple(
        _build_wo_card(
            WorkOrder.objects.select_related("recipe").get(ref=item.ref),
        )
        for item in queue_items
        if item.status == WorkOrder.Status.STARTED
    )

    counts = ProductionCountsProjection(
        total=summary.total_orders,
        planned=summary.planned_orders,
        started=summary.started_orders,
        finished=summary.finished_orders,
        void=summary.void_orders,
        planned_qty=_qty(summary.planned_qty),
        started_qty=_qty(summary.started_qty),
        finished_qty=_qty(summary.finished_qty),
        loss_qty=_qty(summary.loss_qty),
    )

    recipes = tuple(
        RecipeOptionProjection(pk=r.pk, ref=r.ref, name=r.output_ref or r.ref)
        for r in Recipe.objects.filter(is_active=True).order_by("ref")
    )

    positions_qs = Position.objects.all().order_by("name")
    default_pos = Position.objects.filter(is_default=True).first()
    positions = tuple(
        PositionOptionProjection(
            pk=p.pk,
            ref=p.ref,
            name=p.name,
            is_default=p.is_default,
        )
        for p in positions_qs
    )

    return ProductionBoardProjection(
        selected_date=selected_date.isoformat(),
        selected_date_display=selected_date.strftime("%d/%m/%Y"),
        selected_position_ref=position_ref,
        selected_operator_ref=operator_ref,
        work_orders=wo_cards,
        counts=counts,
        planned_queue=planned_queue,
        started_queue=started_queue,
        recipes=recipes,
        positions=positions,
        default_position_pk=default_pos.pk if default_pos else None,
    )


# ── Internals ──────────────────────────────────────────────────────────


def _build_wo_card(wo: WorkOrder) -> WorkOrderCardProjection:
    started_qty = _wo_started_qty(wo)
    finished_qty = wo.finished
    loss = ""
    yield_rate = ""

    if finished_qty is not None:
        base = started_qty or wo.quantity
        if base:
            loss_val = max(base - finished_qty, Decimal("0"))
            loss = str(int(loss_val))
            rate = (finished_qty / base * 100) if base else Decimal("0")
            yield_rate = f"{int(rate)}%"

    return WorkOrderCardProjection(
        pk=wo.pk,
        ref=wo.ref,
        recipe_ref=wo.recipe.ref,
        recipe_name=wo.recipe.output_ref or wo.recipe.ref,
        output_ref=wo.output_ref,
        status=wo.status,
        status_label=WO_STATUS_LABELS.get(wo.status, wo.status),
        status_color=WO_STATUS_COLORS.get(wo.status, "bg-muted text-muted-foreground"),
        planned_qty=str(int(wo.quantity)),
        started_qty=str(int(started_qty)) if started_qty is not None else "",
        finished_qty=str(int(finished_qty)) if finished_qty is not None else "",
        yield_rate=yield_rate,
        loss=loss,
        operator_ref=wo.operator_ref or "",
        position_ref=wo.position_ref or "",
        target_date_display=wo.target_date.strftime("%d/%m/%Y") if wo.target_date else "",
        started_at_display=_format_datetime(wo.started_at) if hasattr(wo, "started_at") and wo.started_at else "",
        created_at_display=_format_datetime(wo.created_at),
        can_void=wo.status in (WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED),
    )


def _wo_started_qty(wo: WorkOrder) -> Decimal | None:
    """Extract started quantity from work order events."""
    if wo.status in (WorkOrder.Status.PLANNED,):
        return None
    for event in wo.events.filter(kind="started").order_by("-seq")[:1]:
        qty = (event.payload or {}).get("quantity")
        if qty is not None:
            return Decimal(str(qty))
    return wo.quantity


def _qty(value: Decimal) -> str:
    if not value:
        return "0"
    return str(int(value))


def _format_datetime(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%d/%m às %H:%M")
