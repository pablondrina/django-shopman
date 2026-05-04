"""ProductionBoardProjection — read models for the production board (Fase 4).

Translates Craftsman work orders, queue items, and summary into immutable
projections for the operator production page. Replaces the inline context
building from ``shopman.backstage.views.production``.

Never imports from ``shopman.backstage.views.*``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone
from shopman.craftsman import craft
from shopman.craftsman.models import Recipe, RecipeItem, WorkOrder
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
class OrderCommitmentProjection:
    """A compact order commitment for a production work order."""

    ref: str
    status: str
    status_label: str
    qty_required: str


@dataclass(frozen=True)
class WorkOrderCardProjection:
    """A single work order card on the production board."""

    pk: int
    ref: str
    recipe_pk: int
    recipe_ref: str
    recipe_name: str
    base_usages: tuple[BaseRecipeUsageProjection, ...]
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
    progress_pct: int
    committed_qty: str
    order_commitments: tuple[OrderCommitmentProjection, ...]
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
class BaseRecipeUsageProjection:
    """How much of a base recipe is used by an output SKU recipe."""

    ref: str
    output_sku: str
    name: str
    quantity_display: str
    per_unit_display: str


@dataclass(frozen=True)
class BaseRecipeOptionProjection:
    """A base recipe available as an operational filter."""

    ref: str
    output_sku: str
    name: str
    count: int


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
    base_usages: tuple[BaseRecipeUsageProjection, ...]
    output_sku: str
    quantity: str
    committed: str
    avg_demand: str
    confidence: str


@dataclass(frozen=True)
class ProductionMatrixRowProjection:
    """A high-volume production matrix row grouped by SKU."""

    recipe_pk: int | None
    output_sku: str
    recipe_name: str
    base_usages: tuple[BaseRecipeUsageProjection, ...]
    suggestion: ProductionSuggestionProjection | None
    planned_orders: tuple[WorkOrderCardProjection, ...]
    started_orders: tuple[WorkOrderCardProjection, ...]
    finished_orders: tuple[WorkOrderCardProjection, ...]
    planned_qty: str
    started_qty: str
    finished_qty: str
    loss_qty: str


@dataclass(frozen=True)
class ProductionMatrixGroupRowProjection:
    """A matrix row within a base recipe group."""

    row: ProductionMatrixRowProjection
    usage: BaseRecipeUsageProjection | None


@dataclass(frozen=True)
class ProductionMatrixGroupProjection:
    """A group of production matrix rows that share a base recipe."""

    ref: str
    output_sku: str
    name: str
    rows: tuple[ProductionMatrixGroupRowProjection, ...]


@dataclass(frozen=True)
class ProductionWeighingIngredientProjection:
    """One ingredient line for a thermal weighing ticket."""

    sku: str
    name: str
    quantity_display: str
    is_subrecipe: bool


@dataclass(frozen=True)
class ProductionWeighingTicketProjection:
    """A printable 80mm-oriented ticket for one recipe/base recipe."""

    recipe_ref: str
    output_sku: str
    name: str
    output_quantity_display: str
    sources_display: str
    ingredients: tuple[ProductionWeighingIngredientProjection, ...]
    table: dict


@dataclass(frozen=True)
class ProductionWeighingProjection:
    """Printable weighing tickets for saved production planning."""

    selected_date: str
    selected_date_display: str
    selected_position_ref: str
    selected_base_recipe: str
    tickets: tuple[ProductionWeighingTicketProjection, ...]


@dataclass(frozen=True)
class _RecipeItemData:
    input_sku: str
    quantity: Decimal
    unit: str
    sort_order: int = 0


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
    selected_base_recipe: str
    work_orders: tuple[WorkOrderCardProjection, ...]
    counts: ProductionCountsProjection
    planned_queue: tuple[WorkOrderCardProjection, ...]
    started_queue: tuple[WorkOrderCardProjection, ...]
    finished_queue: tuple[WorkOrderCardProjection, ...]
    recipes: tuple[RecipeOptionProjection, ...]
    base_recipes: tuple[BaseRecipeOptionProjection, ...]
    positions: tuple[PositionOptionProjection, ...]
    suggestions: tuple[ProductionSuggestionProjection, ...]
    matrix_rows: tuple[ProductionMatrixRowProjection, ...]
    matrix_groups: tuple[ProductionMatrixGroupProjection, ...]
    default_position_pk: int | None
    access: ProductionSurfaceAccess


@dataclass(frozen=True)
class ProductionLateWorkOrderProjection:
    """A started work order that exceeded its configured target window."""

    pk: int
    ref: str
    output_sku: str
    operator_ref: str
    elapsed_minutes: int
    target_minutes: int


@dataclass(frozen=True)
class ProductionDashboardProjection:
    """Top-level read model for the production dashboard."""

    selected_date: str
    selected_date_display: str
    planned_orders: int
    started_orders: int
    finished_orders: int
    void_orders: int
    planned_qty: str
    started_qty: str
    finished_qty: str
    loss_qty: str
    average_yield_rate: str
    capacity_percent: int | None
    late_orders: tuple[ProductionLateWorkOrderProjection, ...]


@dataclass(frozen=True)
class ProductionKDSCardProjection:
    """A started work order card for the production KDS."""

    pk: int
    ref: str
    output_sku: str
    recipe_name: str
    started_qty: str
    operator_ref: str
    position_ref: str
    started_at_display: str
    elapsed_seconds: int
    elapsed_minutes: int
    target_seconds: int
    timer_class: str
    current_step: str
    current_step_index: int | None
    total_steps: int
    current_step_name: str
    step_progress_pct: int
    next_step_name: str
    time_remaining_min: int | None
    can_finish: bool


@dataclass(frozen=True)
class ProductionKDSProjection:
    """Top-level read model for the production KDS."""

    selected_date: str
    selected_date_display: str
    cards: tuple[ProductionKDSCardProjection, ...]
    total_count: int
    late_count: int


@dataclass(frozen=True)
class ProductionReportFilters:
    """Normalized filters for production reports."""

    date_from: date
    date_to: date
    report_kind: str
    recipe_ref: str = ""
    position_ref: str = ""
    operator_ref: str = ""
    status: str = ""


@dataclass(frozen=True)
class WorkOrderReportRow:
    """A work order history row for production audit reports."""

    ref: str
    date: str
    recipe_ref: str
    recipe_name: str
    position_ref: str
    qty_planned: str
    qty_started: str
    qty_finished: str
    qty_loss: str
    yield_rate: str
    operator_ref: str
    started_at: str
    finished_at: str
    duration_minutes: str


@dataclass(frozen=True)
class OperatorProductivityRow:
    """Aggregated productivity by production operator."""

    operator_ref: str
    operator_name: str
    wo_count: int
    qty_total: str
    yield_avg: str
    duration_avg_minutes: str


@dataclass(frozen=True)
class RecipeWasteRow:
    """Aggregated waste by recipe."""

    recipe_ref: str
    recipe_name: str
    wo_count: int
    loss_total: str
    yield_avg: str
    capacity_utilization: str


@dataclass(frozen=True)
class ProductionReportsProjection:
    """Top-level read model for production reports."""

    filters: ProductionReportFilters
    history_rows: tuple[WorkOrderReportRow, ...]
    operator_rows: tuple[OperatorProductivityRow, ...]
    waste_rows: tuple[RecipeWasteRow, ...]
    available_recipes: tuple[RecipeOptionProjection, ...]
    available_positions: tuple[PositionOptionProjection, ...]


# ── Builders ───────────────────────────────────────────────────────────


def build_production_board(
    *,
    selected_date: date | None = None,
    position_ref: str = "",
    operator_ref: str = "",
    base_recipe: str = "",
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
        .prefetch_related("recipe__items")
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
            WorkOrder.objects.select_related("recipe").prefetch_related("recipe__items").get(ref=item.ref),
        )
        for item in queue_items
        if item.status == WorkOrder.Status.PLANNED and access.can_view_planned
    )
    started_queue = tuple(
        _build_wo_card(
            WorkOrder.objects.select_related("recipe").prefetch_related("recipe__items").get(ref=item.ref),
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
    consumed_recipe_skus = set(
        RecipeItem.objects.filter(recipe__is_active=True)
        .exclude(input_sku="")
        .values_list("input_sku", flat=True)
    )
    matrix_recipes = tuple(
        Recipe.objects.filter(is_active=True)
        .exclude(output_sku__in=consumed_recipe_skus)
        .prefetch_related("items")
        .order_by("ref")
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
    visible_suggestions = suggestions if access.can_view_suggested else ()
    all_matrix_rows = _build_matrix_rows(matrix_recipes, wo_cards, visible_suggestions)
    base_recipes = _build_group_options(all_matrix_rows)
    matrix_rows = tuple(
        row for row in all_matrix_rows
        if not base_recipe or any(usage.output_sku == base_recipe for usage in row.base_usages)
    )
    matrix_groups = _build_matrix_groups(matrix_rows, base_recipe=base_recipe)

    return ProductionBoardProjection(
        selected_date=selected_date.isoformat(),
        selected_date_display=selected_date.strftime("%d/%m/%Y"),
        selected_position_ref=position_ref,
        selected_operator_ref=operator_ref,
        selected_base_recipe=base_recipe,
        work_orders=wo_cards,
        counts=counts,
        planned_queue=planned_queue,
        started_queue=started_queue,
        finished_queue=finished_queue,
        recipes=recipes,
        base_recipes=base_recipes,
        positions=positions,
        suggestions=visible_suggestions,
        matrix_rows=matrix_rows,
        matrix_groups=matrix_groups,
        default_position_pk=default_pos.pk if default_pos else None,
        access=access,
    )


def build_production_weighing(
    *,
    selected_date: date | None = None,
    position_ref: str = "",
    base_recipe: str = "",
) -> ProductionWeighingProjection:
    """Build thermal weighing tickets from saved planned/started work orders."""
    selected_date = selected_date or date.today()
    open_statuses = (WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED)
    work_orders = (
        WorkOrder.objects.filter(target_date=selected_date, status__in=open_statuses)
        .select_related("recipe")
        .prefetch_related("recipe__items")
        .order_by("recipe__ref", "output_sku")
    )
    if position_ref:
        work_orders = work_orders.filter(position_ref=position_ref)

    active_recipes = {
        recipe.output_sku: recipe
        for recipe in Recipe.objects.filter(is_active=True).prefetch_related("items").order_by("ref")
    }
    tickets: dict[tuple[int, str], dict] = {}

    def add_ticket(recipe: Recipe, quantity: Decimal, unit: str, source: str) -> None:
        if base_recipe and recipe.output_sku != base_recipe:
            return
        key = (recipe.pk, unit)
        entry = tickets.setdefault(
            key,
            {
                "recipe": recipe,
                "quantity": Decimal("0"),
                "unit": unit,
                "sources": [],
            },
        )
        entry["quantity"] += quantity
        if source not in entry["sources"]:
            entry["sources"].append(source)

    for work_order in work_orders:
        recipe = work_order.recipe
        if not recipe.batch_size:
            continue
        items = _work_order_recipe_items(work_order)
        coefficient = Decimal(str(work_order.quantity)) / recipe.batch_size
        base_items = [
            item for item in items
            if item.input_sku in active_recipes and active_recipes[item.input_sku].pk != recipe.pk
        ]
        source = f"{work_order.output_sku} {_measure(Decimal(str(work_order.quantity)), 'un.')}"

        if base_items:
            for item in base_items:
                add_ticket(
                    active_recipes[item.input_sku],
                    Decimal(str(item.quantity)) * coefficient,
                    item.unit,
                    source,
                )
            continue

        add_ticket(recipe, Decimal(str(work_order.quantity)), "un.", source)

    ingredient_skus = {
        item.input_sku
        for entry in tickets.values()
        for item in _recipe_items(entry["recipe"])
    }
    product_names = _product_names(ingredient_skus)

    return ProductionWeighingProjection(
        selected_date=selected_date.isoformat(),
        selected_date_display=selected_date.strftime("%d/%m/%Y"),
        selected_position_ref=position_ref,
        selected_base_recipe=base_recipe,
        tickets=tuple(
            _build_weighing_ticket(entry, active_recipes=active_recipes, product_names=product_names)
            for entry in sorted(tickets.values(), key=lambda item: item["recipe"].name)
        ),
    )


def build_production_dashboard(
    *,
    selected_date: date | None = None,
    position_ref: str = "",
) -> ProductionDashboardProjection:
    """Build the dashboard projection for the selected production day."""
    selected_date = selected_date or date.today()
    summary = craft.summary(date=selected_date, position_ref=position_ref or None)

    wos = list(
        WorkOrder.objects.filter(target_date=selected_date)
        .select_related("recipe")
        .order_by("created_at")
    )
    if position_ref:
        wos = [wo for wo in wos if wo.position_ref == position_ref]

    finished = [wo for wo in wos if wo.status == WorkOrder.Status.FINISHED and wo.yield_rate is not None]
    if finished:
        average = sum((wo.yield_rate or Decimal("0")) for wo in finished) / Decimal(len(finished))
        average_yield_rate = f"{int(average * 100)}%"
    else:
        average_yield_rate = ""

    capacity_total = Decimal("0")
    planned_total = Decimal("0")
    seen_recipes: set[int] = set()
    for wo in wos:
        planned_total += wo.quantity
        if wo.recipe_id in seen_recipes:
            continue
        seen_recipes.add(wo.recipe_id)
        capacity_total += _decimal_meta(wo.recipe.meta, "capacity_per_day")
    capacity_percent = int((planned_total / capacity_total) * 100) if capacity_total else None

    late = tuple(_late_projection(wo) for wo in wos if _is_late_started(wo))

    return ProductionDashboardProjection(
        selected_date=selected_date.isoformat(),
        selected_date_display=selected_date.strftime("%d/%m/%Y"),
        planned_orders=summary.planned_orders,
        started_orders=summary.started_orders,
        finished_orders=summary.finished_orders,
        void_orders=summary.void_orders,
        planned_qty=_qty(summary.planned_qty),
        started_qty=_qty(summary.started_qty),
        finished_qty=_qty(summary.finished_qty),
        loss_qty=_qty(summary.loss_qty),
        average_yield_rate=average_yield_rate,
        capacity_percent=capacity_percent,
        late_orders=late,
    )


def build_production_kds(
    *,
    selected_date: date | None = None,
    position_ref: str = "",
    access: ProductionSurfaceAccess | None = None,
) -> ProductionKDSProjection:
    """Build a KDS-style board for started production work orders."""
    selected_date = selected_date or date.today()
    access = access or _full_access()

    qs = (
        WorkOrder.objects.filter(
            target_date=selected_date,
            status=WorkOrder.Status.STARTED,
        )
        .select_related("recipe")
        .order_by("started_at", "created_at")
    )
    if position_ref:
        qs = qs.filter(position_ref=position_ref)

    cards = tuple(_build_production_kds_card(wo, access=access) for wo in qs)

    return ProductionKDSProjection(
        selected_date=selected_date.isoformat(),
        selected_date_display=selected_date.strftime("%d/%m/%Y"),
        cards=cards,
        total_count=len(cards),
        late_count=sum(1 for card in cards if card.timer_class == "timer-late"),
    )


def build_production_reports(filters: dict | ProductionReportFilters | None = None) -> ProductionReportsProjection:
    """Build production report rows for the requested filter set."""
    normalized = _normalize_report_filters(filters)
    qs = _report_queryset(normalized)
    work_orders = list(qs)
    history_rows = tuple(_work_order_report_row(wo) for wo in work_orders)

    recipes = tuple(
        RecipeOptionProjection(pk=r.pk, ref=r.ref, name=r.output_sku or r.ref)
        for r in Recipe.objects.filter(is_active=True).order_by("ref")
    )
    positions = tuple(
        PositionOptionProjection(pk=p.pk, ref=p.ref, name=p.name, is_default=p.is_default)
        for p in Position.objects.all().order_by("name")
    )

    return ProductionReportsProjection(
        filters=normalized,
        history_rows=history_rows,
        operator_rows=_operator_productivity_rows(work_orders),
        waste_rows=_recipe_waste_rows(work_orders),
        available_recipes=recipes,
        available_positions=positions,
    )


# ── Internals ──────────────────────────────────────────────────────────


def _build_wo_card(wo: WorkOrder) -> WorkOrderCardProjection:
    started_qty = _wo_started_qty(wo)
    finished_qty = wo.finished
    loss = ""
    yield_rate = ""
    base_usages = _base_recipe_usages(wo.recipe)
    order_commitments = _order_commitments_for_work_order(wo)
    committed_qty = sum((Decimal(item.qty_required) for item in order_commitments), Decimal("0"))

    if finished_qty is not None:
        base = started_qty or wo.quantity
        if base:
            loss_val = max(base - finished_qty, Decimal("0"))
            loss = _qty(loss_val)
            rate = (finished_qty / base * 100) if base else Decimal("0")
            yield_rate = f"{int(rate)}%"

    return WorkOrderCardProjection(
        pk=wo.pk,
        ref=wo.ref,
        recipe_pk=wo.recipe_id,
        recipe_ref=wo.recipe.ref,
        recipe_name=wo.recipe.output_sku or wo.recipe.ref,
        base_usages=base_usages,
        output_sku=wo.output_sku,
        status=wo.status,
        status_label=WO_STATUS_LABELS.get(wo.status, wo.status),
        status_color=WO_STATUS_COLORS.get(wo.status, "bg-muted text-muted-foreground"),
        planned_qty=_qty(wo.quantity),
        started_qty=_qty(started_qty) if started_qty is not None else "",
        finished_qty=_qty(finished_qty) if finished_qty is not None else "",
        yield_rate=yield_rate,
        loss=loss,
        operator_ref=wo.operator_ref or "",
        position_ref=wo.position_ref or "",
        target_date_display=wo.target_date.strftime("%d/%m/%Y") if wo.target_date else "",
        started_at_display=_format_datetime(wo.started_at) if hasattr(wo, "started_at") and wo.started_at else "",
        created_at_display=_format_datetime(wo.created_at),
        progress_pct=_work_order_progress_pct(wo),
        committed_qty=_qty(committed_qty),
        order_commitments=order_commitments,
        can_void=wo.status in (WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED),
    )


def _build_production_kds_card(
    wo: WorkOrder,
    *,
    access: ProductionSurfaceAccess,
) -> ProductionKDSCardProjection:
    now = timezone.now()
    started_at = wo.started_at or wo.created_at
    elapsed = max(0, int((now - started_at).total_seconds()))
    target_minutes = _target_minutes(wo)
    target_seconds = target_minutes * 60
    if elapsed < target_seconds:
        timer_class = "timer-ok"
    elif elapsed < target_seconds * 2:
        timer_class = "timer-warning"
    else:
        timer_class = "timer-late"

    step_state = _production_step_state(wo, elapsed)
    current_step = step_state["current_step_name"] or "Produção"

    return ProductionKDSCardProjection(
        pk=wo.pk,
        ref=wo.ref,
        output_sku=wo.output_sku,
        recipe_name=wo.recipe.name or wo.recipe.ref,
        started_qty=_qty(wo.started_qty or wo.quantity),
        operator_ref=wo.operator_ref or "",
        position_ref=wo.position_ref or "",
        started_at_display=_format_datetime(started_at),
        elapsed_seconds=elapsed,
        elapsed_minutes=elapsed // 60,
        target_seconds=target_seconds,
        timer_class=timer_class,
        current_step=str(current_step),
        current_step_index=step_state["current_step_index"],
        total_steps=step_state["total_steps"],
        current_step_name=step_state["current_step_name"],
        step_progress_pct=step_state["step_progress_pct"],
        next_step_name=step_state["next_step_name"],
        time_remaining_min=step_state["time_remaining_min"],
        can_finish=access.can_edit_finished,
    )


def build_work_order_card(ref: str) -> WorkOrderCardProjection:
    """Build a single work order card by ref for cross-area projections."""
    wo = WorkOrder.objects.select_related("recipe").prefetch_related("recipe__items", "events").get(ref=ref)
    return _build_wo_card(wo)


def _order_commitments_for_work_order(wo: WorkOrder) -> tuple[OrderCommitmentProjection, ...]:
    refs = _linked_order_refs(wo)
    if not refs:
        return ()

    try:
        from shopman.orderman.models import Order

        from shopman.shop.projections.types import ORDER_STATUS_LABELS_PT
    except Exception:
        logger.debug("production.order_ref_import_failed wo=%s", wo.ref, exc_info=True)
        return ()

    orders = (
        Order.objects.filter(ref__in=refs)
        .prefetch_related("items")
        .order_by("created_at")
    )
    by_ref = {order.ref: order for order in orders}
    result: list[OrderCommitmentProjection] = []
    for ref in refs:
        order = by_ref.get(ref)
        if not order:
            continue
        result.append(
            OrderCommitmentProjection(
                ref=order.ref,
                status=order.status,
                status_label=ORDER_STATUS_LABELS_PT.get(order.status, order.status),
                qty_required=_qty(_qty_required_for_order(order, wo.output_sku)),
            )
        )
    return tuple(result)


def _linked_order_refs(wo: WorkOrder) -> tuple[str, ...]:
    try:
        from shopman.shop.handlers.production_order_sync import linked_order_refs
    except Exception:
        logger.debug("production.order_ref_key_import_failed wo=%s", wo.ref, exc_info=True)
        return ()
    return linked_order_refs(wo)


def _qty_required_for_order(order, sku: str) -> Decimal:
    total = Decimal("0")
    for item in order.items.all():
        if item.sku == sku:
            total += item.qty
    return total


def _work_order_progress_pct(wo: WorkOrder) -> int:
    base = wo.quantity or Decimal("0")
    if base <= 0:
        return 0
    if wo.status == WorkOrder.Status.FINISHED and wo.finished is not None:
        value = (wo.finished / base) * 100
    elif wo.status == WorkOrder.Status.STARTED:
        value = ((_wo_started_qty(wo) or Decimal("0")) / base) * 100
    else:
        value = Decimal("0")
    return max(0, min(100, int(value)))


def _production_step_state(wo: WorkOrder, elapsed_seconds: int) -> dict[str, int | str | None]:
    steps = _recipe_steps(wo.recipe)
    if not steps:
        return {
            "current_step_index": None,
            "total_steps": 0,
            "current_step_name": "",
            "step_progress_pct": 0,
            "next_step_name": "",
            "time_remaining_min": None,
        }

    override_index = _manual_step_index(wo.meta, total=len(steps))
    elapsed = max(0, elapsed_seconds)
    elapsed_before = 0
    current_index = 1
    current_step = steps[0]

    if override_index is not None:
        current_index = override_index
        current_step = steps[current_index - 1]
        elapsed_before = sum(step["target_seconds"] for step in steps[: current_index - 1])
    else:
        for index, step in enumerate(steps, start=1):
            target = step["target_seconds"]
            if elapsed < elapsed_before + target or index == len(steps):
                current_index = index
                current_step = step
                break
            elapsed_before += target

    target_seconds = max(1, current_step["target_seconds"])
    elapsed_in_step = max(0, elapsed - elapsed_before)
    progress = max(0, min(100, int((Decimal(elapsed_in_step) / Decimal(target_seconds)) * 100)))
    next_step = steps[current_index] if current_index < len(steps) else None
    remaining = max(0, elapsed_before + target_seconds - elapsed)

    return {
        "current_step_index": current_index,
        "total_steps": len(steps),
        "current_step_name": current_step["name"],
        "step_progress_pct": progress,
        "next_step_name": next_step["name"] if next_step else "",
        "time_remaining_min": int((remaining + 59) // 60) if next_step else None,
    }


def _recipe_steps(recipe: Recipe) -> list[dict[str, int | str]]:
    raw_steps = (recipe.meta or {}).get("steps") or recipe.steps or []
    result: list[dict[str, int | str]] = []
    for index, raw in enumerate(raw_steps, start=1):
        if isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("label") or f"Passo {index}").strip()
            target = raw.get("target_seconds") or raw.get("seconds") or raw.get("target")
        else:
            name = str(raw or f"Passo {index}").strip()
            target = None
        try:
            target_seconds = int(target or 0)
        except (TypeError, ValueError):
            target_seconds = 0
        result.append({
            "name": name or f"Passo {index}",
            "target_seconds": max(1, target_seconds or int(_target_minutes_for_recipe(recipe) * 60 / max(1, len(raw_steps)))),
        })
    return result


def _manual_step_index(meta: dict | None, *, total: int) -> int | None:
    raw = (meta or {}).get("steps_progress")
    if raw in (None, ""):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return max(1, min(total, value))


def _target_minutes_for_recipe(recipe: Recipe) -> int:
    return int(_decimal_meta(recipe.meta, "max_started_minutes") or Decimal("240"))


def _normalize_report_filters(filters: dict | ProductionReportFilters | None) -> ProductionReportFilters:
    if isinstance(filters, ProductionReportFilters):
        return filters
    raw = filters or {}
    today = date.today()
    date_to = _parse_date(raw.get("date_to"), today)
    date_from = _parse_date(raw.get("date_from"), date_to - timedelta(days=6))
    if date_from > date_to:
        date_from, date_to = date_to, date_from
    report_kind = str(raw.get("report_kind") or raw.get("kind") or "history").strip()
    if report_kind not in {"history", "operator_productivity", "recipe_waste"}:
        report_kind = "history"
    status = str(raw.get("status") or "").strip()
    if status not in {"", *WorkOrder.Status.values}:
        status = ""
    return ProductionReportFilters(
        date_from=date_from,
        date_to=date_to,
        report_kind=report_kind,
        recipe_ref=str(raw.get("recipe_ref") or "").strip(),
        position_ref=str(raw.get("position_ref") or "").strip(),
        operator_ref=str(raw.get("operator_ref") or "").strip(),
        status=status,
    )


def _parse_date(value, default: date) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return default


def _report_queryset(filters: ProductionReportFilters):
    qs = (
        WorkOrder.objects
        .filter(target_date__gte=filters.date_from, target_date__lte=filters.date_to)
        .select_related("recipe")
        .prefetch_related("events")
        .order_by("target_date", "recipe__ref", "ref")
    )
    if filters.recipe_ref:
        qs = qs.filter(recipe__ref=filters.recipe_ref)
    if filters.position_ref:
        qs = qs.filter(position_ref=filters.position_ref)
    if filters.operator_ref:
        qs = qs.filter(operator_ref=filters.operator_ref)
    if filters.status:
        qs = qs.filter(status=filters.status)
    return qs


def _work_order_report_row(wo: WorkOrder) -> WorkOrderReportRow:
    started_qty = _wo_started_qty(wo) or Decimal("0")
    finished_qty = wo.finished or Decimal("0")
    loss_qty = max((started_qty or wo.quantity) - finished_qty, Decimal("0")) if wo.finished is not None else Decimal("0")
    yield_rate = ""
    if wo.finished is not None and (started_qty or wo.quantity):
        yield_rate = f"{int((finished_qty / (started_qty or wo.quantity)) * 100)}%"
    duration = _duration_minutes(wo.started_at, wo.finished_at)
    return WorkOrderReportRow(
        ref=wo.ref,
        date=wo.target_date.isoformat() if wo.target_date else "",
        recipe_ref=wo.recipe.ref,
        recipe_name=wo.recipe.name or wo.recipe.ref,
        position_ref=wo.position_ref or "",
        qty_planned=_qty(wo.quantity),
        qty_started=_qty(started_qty) if started_qty else "",
        qty_finished=_qty(finished_qty) if wo.finished is not None else "",
        qty_loss=_qty(loss_qty) if loss_qty else "0",
        yield_rate=yield_rate,
        operator_ref=wo.operator_ref or "",
        started_at=_format_datetime(wo.started_at) if wo.started_at else "",
        finished_at=_format_datetime(wo.finished_at) if wo.finished_at else "",
        duration_minutes=str(duration) if duration is not None else "",
    )


def _operator_productivity_rows(work_orders: list[WorkOrder]) -> tuple[OperatorProductivityRow, ...]:
    grouped: dict[str, dict[str, object]] = {}
    for wo in work_orders:
        if wo.status != WorkOrder.Status.FINISHED:
            continue
        operator = wo.operator_ref or "sem-operador"
        bucket = grouped.setdefault(operator, {"count": 0, "qty": Decimal("0"), "yield": [], "duration": []})
        bucket["count"] = int(bucket["count"]) + 1
        bucket["qty"] = bucket["qty"] + (wo.finished or Decimal("0"))
        base = _wo_started_qty(wo) or wo.quantity
        if base:
            bucket["yield"].append((wo.finished or Decimal("0")) / base)
        duration = _duration_minutes(wo.started_at, wo.finished_at)
        if duration is not None:
            bucket["duration"].append(duration)
    return tuple(
        OperatorProductivityRow(
            operator_ref=operator,
            operator_name=operator.replace("chef:", "").replace("production:", "") or "Sem operador",
            wo_count=int(data["count"]),
            qty_total=_qty(data["qty"]),
            yield_avg=_percent_avg(data["yield"]),
            duration_avg_minutes=_int_avg_display(data["duration"]),
        )
        for operator, data in sorted(grouped.items(), key=lambda item: item[0])
    )


def _recipe_waste_rows(work_orders: list[WorkOrder]) -> tuple[RecipeWasteRow, ...]:
    grouped: dict[str, dict[str, object]] = {}
    for wo in work_orders:
        if wo.status != WorkOrder.Status.FINISHED:
            continue
        bucket = grouped.setdefault(
            wo.recipe.ref,
            {"name": wo.recipe.name or wo.recipe.ref, "count": 0, "loss": Decimal("0"), "yield": [], "planned": Decimal("0")},
        )
        bucket["count"] = int(bucket["count"]) + 1
        started = _wo_started_qty(wo) or wo.quantity
        finished = wo.finished or Decimal("0")
        bucket["planned"] = bucket["planned"] + wo.quantity
        bucket["loss"] = bucket["loss"] + max(started - finished, Decimal("0"))
        if started:
            bucket["yield"].append(finished / started)
    rows = [
        RecipeWasteRow(
            recipe_ref=recipe_ref,
            recipe_name=str(data["name"]),
            wo_count=int(data["count"]),
            loss_total=_qty(data["loss"]),
            yield_avg=_percent_avg(data["yield"]),
            capacity_utilization="",
        )
        for recipe_ref, data in grouped.items()
    ]
    return tuple(sorted(rows, key=lambda row: Decimal(row.loss_total or "0"), reverse=True)[:10])


def _duration_minutes(started_at, finished_at) -> int | None:
    if not started_at or not finished_at:
        return None
    return max(0, int((finished_at - started_at).total_seconds() // 60))


def _percent_avg(values: list[Decimal]) -> str:
    if not values:
        return ""
    return f"{int((sum(values) / Decimal(len(values))) * 100)}%"


def _int_avg_display(values: list[int]) -> str:
    if not values:
        return ""
    return str(int(sum(values) / len(values)))


def _is_late_started(wo: WorkOrder) -> bool:
    if wo.status != WorkOrder.Status.STARTED:
        return False
    started_at = wo.started_at or wo.created_at
    elapsed_minutes = int((timezone.now() - started_at).total_seconds() // 60)
    return elapsed_minutes > _target_minutes(wo)


def _late_projection(wo: WorkOrder) -> ProductionLateWorkOrderProjection:
    started_at = wo.started_at or wo.created_at
    elapsed_minutes = int((timezone.now() - started_at).total_seconds() // 60)
    return ProductionLateWorkOrderProjection(
        pk=wo.pk,
        ref=wo.ref,
        output_sku=wo.output_sku,
        operator_ref=wo.operator_ref or "",
        elapsed_minutes=elapsed_minutes,
        target_minutes=_target_minutes(wo),
    )


def _target_minutes(wo: WorkOrder) -> int:
    return int(_decimal_meta(wo.recipe.meta, "max_started_minutes") or Decimal("240"))


def _decimal_meta(meta: dict, key: str) -> Decimal:
    try:
        value = (meta or {}).get(key)
        if value in (None, ""):
            return Decimal("0")
        decimal = Decimal(str(value))
        return decimal if decimal > 0 else Decimal("0")
    except Exception:
        logger.debug("decimal_meta_parse_failed key=%s", key, exc_info=True)
        return Decimal("0")


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
    base_usages = _base_recipe_usages(suggestion.recipe)
    return ProductionSuggestionProjection(
        recipe_pk=suggestion.recipe.pk,
        recipe_ref=suggestion.recipe.ref,
        recipe_name=suggestion.recipe.name or suggestion.recipe.ref,
        base_usages=base_usages,
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


def _build_matrix_rows(
    recipes: tuple[Recipe, ...],
    work_orders: tuple[WorkOrderCardProjection, ...],
    suggestions: tuple[ProductionSuggestionProjection, ...],
) -> tuple[ProductionMatrixRowProjection, ...]:
    rows: dict[str, dict] = {}

    def row_for(output_sku: str) -> dict:
        return rows.setdefault(
            output_sku,
            {
                "recipe_pk": None,
                "recipe_name": output_sku,
                "base_usages": (),
                "suggestion": None,
                "planned": [],
                "started": [],
                "finished": [],
            },
        )

    for recipe in recipes:
        row = row_for(recipe.output_sku)
        row["recipe_pk"] = recipe.pk
        row["recipe_name"] = recipe.output_sku or recipe.ref
        row["base_usages"] = _base_recipe_usages(recipe)

    for suggestion in suggestions:
        row = row_for(suggestion.output_sku)
        row["recipe_pk"] = suggestion.recipe_pk
        row["recipe_name"] = suggestion.recipe_name or suggestion.output_sku
        row["base_usages"] = suggestion.base_usages
        row["suggestion"] = suggestion

    for work_order in work_orders:
        row = row_for(work_order.output_sku)
        row["recipe_pk"] = work_order.recipe_pk
        row["recipe_name"] = work_order.recipe_name or row["recipe_name"]
        row["base_usages"] = work_order.base_usages
        if work_order.status == WorkOrder.Status.PLANNED:
            row["planned"].append(work_order)
        elif work_order.status == WorkOrder.Status.STARTED:
            row["started"].append(work_order)
        elif work_order.status == WorkOrder.Status.FINISHED:
            row["finished"].append(work_order)

    return tuple(
        ProductionMatrixRowProjection(
            recipe_pk=row["recipe_pk"],
            output_sku=output_sku,
            recipe_name=row["recipe_name"],
            base_usages=row["base_usages"],
            suggestion=row["suggestion"],
            planned_orders=tuple(row["planned"]),
            started_orders=tuple(row["started"]),
            finished_orders=tuple(row["finished"]),
            planned_qty=_sum_qty(row["planned"], "planned_qty"),
            started_qty=_sum_qty(row["started"], "started_qty"),
            finished_qty=_sum_qty(row["finished"], "finished_qty"),
            loss_qty=_sum_qty(row["finished"], "loss"),
        )
        for output_sku, row in sorted(rows.items(), key=lambda item: item[0])
    )


def _build_group_options(
    matrix_rows: tuple[ProductionMatrixRowProjection, ...],
) -> tuple[BaseRecipeOptionProjection, ...]:
    groups: dict[str, dict[str, int | str]] = {}
    for row in matrix_rows:
        for usage in row.base_usages:
            group = groups.setdefault(
                usage.output_sku,
                {"ref": usage.ref, "name": usage.name, "count": 0},
            )
            group["count"] = int(group["count"]) + 1

    return tuple(
        BaseRecipeOptionProjection(
            ref=str(data["ref"]),
            output_sku=output_sku,
            name=str(data["name"]),
            count=int(data["count"]),
        )
        for ref, data in sorted(groups.items(), key=lambda item: str(item[1]["name"]))
        for output_sku in (ref,)
    )


def _build_matrix_groups(
    matrix_rows: tuple[ProductionMatrixRowProjection, ...],
    *,
    base_recipe: str = "",
) -> tuple[ProductionMatrixGroupProjection, ...]:
    grouped: dict[str, dict] = {}
    for row in matrix_rows:
        usages = row.base_usages
        if base_recipe:
            usages = tuple(usage for usage in usages if usage.output_sku == base_recipe)
        if not usages:
            group = grouped.setdefault("__direct__", {"name": "Receitas diretas", "output_sku": "", "rows": []})
            group["rows"].append(ProductionMatrixGroupRowProjection(row=row, usage=None))
            continue
        for usage in usages:
            group = grouped.setdefault(
                usage.output_sku,
                {"name": usage.name, "output_sku": usage.output_sku, "rows": []},
            )
            group["rows"].append(ProductionMatrixGroupRowProjection(row=row, usage=usage))

    return tuple(
        ProductionMatrixGroupProjection(
            ref=ref,
            output_sku=str(data["output_sku"]),
            name=data["name"],
            rows=tuple(data["rows"]),
        )
        for ref, data in sorted(grouped.items(), key=lambda item: item[1]["name"])
    )


def _sum_qty(work_orders: list[WorkOrderCardProjection], field_name: str) -> str:
    total = Decimal("0")
    for work_order in work_orders:
        raw = getattr(work_order, field_name, "") or "0"
        total += Decimal(str(raw))
    return _qty(total)


def _base_recipe_usages(recipe: Recipe) -> tuple[BaseRecipeUsageProjection, ...]:
    prefetched = getattr(recipe, "_prefetched_objects_cache", {}).get("items")
    if prefetched is not None:
        items = tuple(item for item in prefetched if not item.is_optional)
    else:
        items = tuple(recipe.items.filter(is_optional=False).order_by("sort_order"))
    if not items:
        return ()
    base_recipes = {
        base.output_sku: base
        for base in Recipe.objects.filter(
            is_active=True,
            output_sku__in=[item.input_sku for item in items],
        )
    }
    return tuple(
        BaseRecipeUsageProjection(
            ref=base_recipes[item.input_sku].ref,
            output_sku=base_recipes[item.input_sku].output_sku,
            name=base_recipes[item.input_sku].name or base_recipes[item.input_sku].output_sku,
            quantity_display=_measure(item.quantity, item.unit),
            per_unit_display=_measure(item.quantity / recipe.batch_size, item.unit),
        )
        for item in items
        if item.input_sku in base_recipes
    )


def _build_weighing_ticket(
    entry: dict,
    *,
    active_recipes: dict[str, Recipe],
    product_names: dict[str, str],
) -> ProductionWeighingTicketProjection:
    recipe = entry["recipe"]
    output_quantity = Decimal(str(entry["quantity"]))
    output_unit = str(entry["unit"])
    coefficient = output_quantity / recipe.batch_size
    ingredients = tuple(
        ProductionWeighingIngredientProjection(
            sku=item.input_sku,
            name=_ingredient_name(item.input_sku, active_recipes=active_recipes, product_names=product_names),
            quantity_display=_measure(Decimal(str(item.quantity)) * coefficient, item.unit),
            is_subrecipe=item.input_sku in active_recipes,
        )
        for item in _recipe_items(recipe)
    )
    table = {
        "headers": ["Insumo", "Quantidade"],
        "rows": [
            {"cols": [ingredient.name, ingredient.quantity_display]}
            for ingredient in ingredients
        ],
    }
    return ProductionWeighingTicketProjection(
        recipe_ref=recipe.ref,
        output_sku=recipe.output_sku,
        name=recipe.name,
        output_quantity_display=_measure(output_quantity, output_unit),
        sources_display=", ".join(entry["sources"]),
        ingredients=ingredients,
        table=table,
    )


def _recipe_items(recipe: Recipe) -> tuple[_RecipeItemData, ...]:
    prefetched = getattr(recipe, "_prefetched_objects_cache", {}).get("items")
    if prefetched is not None:
        return tuple(
            _RecipeItemData(
                input_sku=item.input_sku,
                quantity=Decimal(str(item.quantity)),
                unit=item.unit,
                sort_order=item.sort_order,
            )
            for item in sorted((item for item in prefetched if not item.is_optional), key=lambda item: item.sort_order)
        )
    return tuple(
        _RecipeItemData(
            input_sku=item.input_sku,
            quantity=Decimal(str(item.quantity)),
            unit=item.unit,
            sort_order=item.sort_order,
        )
        for item in recipe.items.filter(is_optional=False).order_by("sort_order")
    )


def _work_order_recipe_items(work_order: WorkOrder) -> tuple[_RecipeItemData, ...]:
    snapshot = (work_order.meta or {}).get("_recipe_snapshot")
    if not snapshot:
        return _recipe_items(work_order.recipe)
    return tuple(
        _RecipeItemData(
            input_sku=str(item["input_sku"]),
            quantity=Decimal(str(item["quantity"])),
            unit=str(item.get("unit") or "un"),
            sort_order=index,
        )
        for index, item in enumerate(snapshot.get("items") or [])
    )


def _ingredient_name(
    sku: str,
    *,
    active_recipes: dict[str, Recipe],
    product_names: dict[str, str],
) -> str:
    if sku in active_recipes:
        recipe = active_recipes[sku]
        return f"{recipe.name} ({sku})"
    return product_names.get(sku, sku)


def _product_names(skus: set[str]) -> dict[str, str]:
    if not skus:
        return {}
    try:
        from shopman.offerman.models import Product
    except Exception:
        logger.debug("production.product_names_import_failed", exc_info=True)
        return {}
    return dict(Product.objects.filter(sku__in=skus).values_list("sku", "name"))


def _measure(value: Decimal, unit: str) -> str:
    normalized = value.quantize(Decimal("0.001")).normalize()
    text = format(normalized, "f").replace(".", ",")
    return f"{text} {unit}".strip()


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
    return format(value.quantize(Decimal("0.001")).normalize(), "f")


def _format_datetime(dt) -> str:
    if dt is None:
        return ""
    local = timezone.localtime(dt)
    return local.strftime("%d/%m às %H:%M")
