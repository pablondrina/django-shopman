"""ProductionBoardProjection — read models for the production board (Fase 4).

Translates Craftsman work orders, queue items, and summary into immutable
projections for the operator production page. Replaces the inline context
building from ``shopman.backstage.views.production``.

Never imports from ``shopman.backstage.views.*``.
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
    output_sku: str
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
    name: str  # output_sku or recipe ref display


@dataclass(frozen=True)
class PositionOptionProjection:
    """A stock position available for production form."""

    pk: int
    ref: str
    name: str
    is_default: bool


@dataclass(frozen=True)
class ProductionSuggestionProjection:
    """A suggested production row from Craftsman demand planning."""

    recipe_pk: int
    recipe_ref: str
    recipe_name: str
    output_sku: str
    quantity: str
    committed: str
    avg_demand: str
    confidence: str


@dataclass(frozen=True)
class ProductionSurfaceAccess:
    """Column-level access for the production board surface."""

    can_manage_all: bool
    can_view_suggested: bool
    can_edit_suggested: bool
    can_view_planned: bool
    can_edit_planned: bool
    can_view_started: bool
    can_edit_started: bool
    can_view_finished: bool
    can_edit_finished: bool
    can_view_unsold: bool
    can_edit_unsold: bool

    @property
    def can_access_board(self) -> bool:
        return any((
            self.can_manage_all,
            self.can_view_suggested,
            self.can_edit_suggested,
            self.can_view_planned,
            self.can_edit_planned,
            self.can_view_started,
            self.can_edit_started,
            self.can_view_finished,
            self.can_edit_finished,
            self.can_view_unsold,
            self.can_edit_unsold,
        ))

    @property
    def can_see_current_kernel_columns(self) -> bool:
        return self.can_view_planned or self.can_view_started or self.can_view_finished


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
    finished_queue: tuple[WorkOrderCardProjection, ...]
    recipes: tuple[RecipeOptionProjection, ...]
    positions: tuple[PositionOptionProjection, ...]
    suggestions: tuple[ProductionSuggestionProjection, ...]
    default_position_pk: int | None
    access: ProductionSurfaceAccess


# ── Builders ───────────────────────────────────────────────────────────


def build_production_board(
    *,
    selected_date: date | None = None,
    position_ref: str = "",
    operator_ref: str = "",
    access: ProductionSurfaceAccess | None = None,
) -> ProductionBoardProjection:
    """Build the production board projection."""
    selected_date = selected_date or date.today()
    access = access or _full_access()

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

    wo_cards = tuple(
        card for card in (_build_wo_card(wo) for wo in wos_qs)
        if _can_view_card(card, access)
    )

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
        if item.status == WorkOrder.Status.PLANNED and access.can_view_planned
    )
    started_queue = tuple(
        _build_wo_card(
            WorkOrder.objects.select_related("recipe").get(ref=item.ref),
        )
        for item in queue_items
        if item.status == WorkOrder.Status.STARTED and access.can_view_started
    )
    finished_queue = tuple(
        wo for wo in wo_cards
        if wo.status == WorkOrder.Status.FINISHED and access.can_view_finished
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
        RecipeOptionProjection(pk=r.pk, ref=r.ref, name=r.output_sku or r.ref)
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
    suggestions = tuple(_build_suggestion(s) for s in _production_suggestions(selected_date))

    return ProductionBoardProjection(
        selected_date=selected_date.isoformat(),
        selected_date_display=selected_date.strftime("%d/%m/%Y"),
        selected_position_ref=position_ref,
        selected_operator_ref=operator_ref,
        work_orders=wo_cards,
        counts=counts,
        planned_queue=planned_queue,
        started_queue=started_queue,
        finished_queue=finished_queue,
        recipes=recipes,
        positions=positions,
        suggestions=suggestions if access.can_view_suggested else (),
        default_position_pk=default_pos.pk if default_pos else None,
        access=access,
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
        recipe_name=wo.recipe.output_sku or wo.recipe.ref,
        output_sku=wo.output_sku,
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


def _production_suggestions(selected_date: date) -> list:
    try:
        return craft.suggest(date=selected_date)
    except Exception:
        logger.exception("production_suggestions_failed date=%s", selected_date)
        return []


def _build_suggestion(suggestion) -> ProductionSuggestionProjection:
    basis = suggestion.basis or {}
    avg = basis.get("avg_demand", Decimal("0")) or Decimal("0")
    committed = basis.get("committed", Decimal("0")) or Decimal("0")
    confidence = str(basis.get("confidence", "") or "")
    return ProductionSuggestionProjection(
        recipe_pk=suggestion.recipe.pk,
        recipe_ref=suggestion.recipe.ref,
        recipe_name=suggestion.recipe.name or suggestion.recipe.ref,
        output_sku=suggestion.recipe.output_sku,
        quantity=_qty(suggestion.quantity),
        committed=_qty(committed),
        avg_demand=f"{avg:.1f}" if avg else "0",
        confidence={
            "high": "Alta",
            "medium": "Média",
            "low": "Baixa",
        }.get(confidence, "Sem histórico"),
    )


def resolve_production_access(user) -> ProductionSurfaceAccess:
    """Resolve canonical column access for the production surface."""
    if getattr(user, "is_superuser", False) or user.has_perm("shop.manage_production"):
        return _full_access()

    def view(column: str) -> bool:
        return user.has_perm(f"shop.view_production_{column}") or edit(column)

    def edit(column: str) -> bool:
        return user.has_perm(f"shop.edit_production_{column}")

    return ProductionSurfaceAccess(
        can_manage_all=False,
        can_view_suggested=view("suggested"),
        can_edit_suggested=edit("suggested"),
        can_view_planned=view("planned"),
        can_edit_planned=edit("planned"),
        can_view_started=view("started"),
        can_edit_started=edit("started"),
        can_view_finished=view("finished"),
        can_edit_finished=edit("finished"),
        can_view_unsold=view("unsold"),
        can_edit_unsold=edit("unsold"),
    )


def _full_access() -> ProductionSurfaceAccess:
    return ProductionSurfaceAccess(
        can_manage_all=True,
        can_view_suggested=True,
        can_edit_suggested=True,
        can_view_planned=True,
        can_edit_planned=True,
        can_view_started=True,
        can_edit_started=True,
        can_view_finished=True,
        can_edit_finished=True,
        can_view_unsold=True,
        can_edit_unsold=True,
    )


def _can_view_card(card: WorkOrderCardProjection, access: ProductionSurfaceAccess) -> bool:
    if card.status == WorkOrder.Status.PLANNED:
        return access.can_view_planned
    if card.status == WorkOrder.Status.STARTED:
        return access.can_view_started
    if card.status == WorkOrder.Status.FINISHED:
        return access.can_view_finished
    return access.can_manage_all


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
