"""
Query service — suggest, needs, expected.

Read-only operations. All @classmethod (mixin pattern).
"""

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Sum

logger = logging.getLogger(__name__)


@dataclass
class Need:
    """Material need from BOM explosion."""
    item_ref: str
    quantity: Decimal
    unit: str
    has_recipe: bool


@dataclass
class Suggestion:
    """Production suggestion for a date."""
    recipe: object  # Recipe instance
    quantity: Decimal
    basis: dict = field(default_factory=dict)


@dataclass
class CraftQueueItem:
    """Operational queue row for the production floor."""

    ref: str
    recipe_ref: str
    output_sku: str
    status: str
    target_date: object
    position_ref: str
    operator_ref: str
    planned_qty: Decimal
    started_qty: Decimal | None
    finished_qty: Decimal | None
    loss_qty: Decimal | None
    yield_rate: Decimal | None


@dataclass
class CraftSummary:
    """Operational summary for a floor/date slice."""

    total_orders: int = 0
    planned_orders: int = 0
    started_orders: int = 0
    finished_orders: int = 0
    void_orders: int = 0
    planned_qty: Decimal = Decimal("0")
    started_qty: Decimal = Decimal("0")
    finished_qty: Decimal = Decimal("0")
    loss_qty: Decimal = Decimal("0")


class CraftQueries:
    """Read-only query methods."""

    @classmethod
    def expected(cls, output_sku, date):
        """
        Sum of active WorkOrder quantities for output_sku on date.

        Used by the availability system (spec 016).

        Returns:
            Decimal — total planned quantity.
        """
        from shopman.craftsman.models import WorkOrder

        result = WorkOrder.objects.filter(
            output_sku=output_sku,
            status__in=[WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED],
            target_date=date,
        ).aggregate(total=Sum("quantity"))
        return result["total"] or Decimal("0")

    @classmethod
    def needs(cls, date, expand=False):
        """
        BOM explosion for a date. Returns material needs.

        Args:
            date: production date
            expand: if True, recursively expand sub-recipes to raw materials

        Returns:
            list[Need] — aggregated material needs.
        """
        from shopman.craftsman.models import WorkOrder

        orders = WorkOrder.objects.filter(
            status__in=[WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED],
            target_date=date,
        ).select_related("recipe").prefetch_related("recipe__items")

        aggregated = {}
        for wo in orders:
            coefficient = wo.quantity / wo.recipe.batch_size
            for ri in wo.recipe.items.filter(is_optional=False).order_by("sort_order"):
                if expand:
                    for item_ref, qty, unit in _expand_bom(ri.input_sku, ri.quantity * coefficient, ri.unit):
                        _aggregate(aggregated, item_ref, qty, unit)
                else:
                    _aggregate(aggregated, ri.input_sku, ri.quantity * coefficient, ri.unit)

        return list(aggregated.values())

    @classmethod
    def suggest(
        cls,
        date,
        output_skus=None,
        *,
        season_months: list | None = None,
        high_demand_multiplier: Decimal | None = None,
    ):
        """
        Suggest production quantities for a date.

        Args:
            date: production date
            output_skus: optional list of output_sku strings to filter recipes.
                         If None, all active recipes are considered.
            season_months: optional list of month ints to filter history by season.
                           e.g. [10, 11, 12, 1, 2, 3] for hot season.
                           If None, all history months are used.
            high_demand_multiplier: if provided and the date falls on Friday (4) or
                                    Saturday (5), multiply suggested qty by this factor.

        Algorithm:
            For each active Recipe (optionally filtered by output_skus):
            1. Get historical demand via DemandProtocol.history()
            2. Filter by season_months if provided
            3. Estimate true demand (extrapolate if soldout_at set)
            4. confidence = "high" / "medium" / "low" based on sample_size
            5. avg_demand = average of estimates
            6. Apply waste adjustment if waste_rate > 15%
            7. committed = DemandProtocol.committed(output_sku, date)
            8. quantity = (avg_demand + committed) * (1 + SAFETY_STOCK_PERCENT)
            9. Apply high_demand_multiplier on Fri/Sat if provided

        Returns [] if DEMAND_BACKEND is not configured.
        """
        from shopman.craftsman.conf import get_setting
        from shopman.craftsman.models import Recipe

        backend_path = get_setting("DEMAND_BACKEND")
        if not backend_path:
            return []

        try:
            from django.utils.module_loading import import_string

            backend = import_string(backend_path)()
        except Exception:
            logger.warning("Failed to load DEMAND_BACKEND: %s", backend_path)
            return []

        safety_pct = get_setting("SAFETY_STOCK_PERCENT")
        historical_days = get_setting("HISTORICAL_DAYS")
        same_weekday = get_setting("SAME_WEEKDAY_ONLY")

        suggestions = []
        recipes = Recipe.objects.filter(is_active=True)
        if output_skus:
            recipes = recipes.filter(output_sku__in=output_skus)
        for recipe in recipes:
            history = backend.history(
                recipe.output_sku,
                days=historical_days,
                same_weekday=same_weekday,
            )

            if not history:
                continue

            # Filter by season if provided
            if season_months:
                history = [dd for dd in history if dd.date.month in season_months]

            # Estimate true demand for each historical day
            estimates = [_estimate_demand(dd) for dd in history]

            # Confidence based on sample size
            confidence = _calc_confidence(len(estimates))
            if confidence is None:
                # Not enough data — skip this recipe
                continue

            avg_demand = sum(estimates) / len(estimates)

            # Waste adjustment: if waste_rate > 15%, reduce proportionally
            total_sold = sum(dd.sold for dd in history)
            total_wasted = sum(dd.wasted for dd in history)
            waste_rate: Decimal | None = None
            if total_sold > 0 and total_wasted > 0:
                waste_rate = total_wasted / total_sold
                if waste_rate > Decimal("0.15"):
                    avg_demand = avg_demand * (1 - waste_rate)

            committed = backend.committed(recipe.output_sku, date)

            raw_qty = (avg_demand + committed) * (1 + safety_pct)

            # High demand multiplier: Fri(4) or Sat(5)
            high_demand_applied = False
            if high_demand_multiplier and date.weekday() in (4, 5):
                raw_qty = raw_qty * high_demand_multiplier
                high_demand_applied = True

            quantity = raw_qty.quantize(Decimal("1"))  # round to whole units

            # Determine season label
            season_label: str | None = None
            if season_months:
                season_label = _season_label(season_months)

            suggestions.append(
                Suggestion(
                    recipe=recipe,
                    quantity=quantity,
                    basis={
                        "avg_demand": avg_demand,
                        "committed": committed,
                        "safety_pct": safety_pct,
                        "historical_days": historical_days,
                        "same_weekday": same_weekday,
                        "sample_size": len(estimates),
                        "confidence": confidence,
                        "season": season_label,
                        "waste_rate": waste_rate,
                        "high_demand_applied": high_demand_applied,
                    },
                )
            )

        return suggestions

    @classmethod
    def queue(
        cls,
        *,
        date=None,
        position_ref: str | None = None,
        operator_ref: str | None = None,
        statuses: list[str] | None = None,
    ) -> list[CraftQueueItem]:
        """
        Operational queue for the floor.

        Defaults to active work (`planned` + `started`) because this is the
        practical queue the floor needs to act on.
        """
        from shopman.craftsman.models import WorkOrder

        statuses = statuses or [WorkOrder.Status.PLANNED, WorkOrder.Status.STARTED]
        orders = cls._queue_queryset(
            date=date,
            position_ref=position_ref,
            operator_ref=operator_ref,
            statuses=statuses,
        )

        items = []
        for order in orders:
            started_qty = _started_qty(order)
            finished_qty = order.finished
            loss_qty = None
            yield_rate = None
            if finished_qty is not None:
                base_qty = started_qty or order.quantity
                loss_qty = max(base_qty - finished_qty, Decimal("0"))
                yield_rate = (finished_qty / base_qty) if base_qty else None

            items.append(
                CraftQueueItem(
                    ref=order.ref,
                    recipe_ref=order.recipe.ref,
                    output_sku=order.output_sku,
                    status=order.status,
                    target_date=order.target_date,
                    position_ref=order.position_ref or "",
                    operator_ref=order.operator_ref or "",
                    planned_qty=order.quantity,
                    started_qty=started_qty,
                    finished_qty=finished_qty,
                    loss_qty=loss_qty,
                    yield_rate=yield_rate,
                )
            )
        return items

    @classmethod
    def summary(
        cls,
        *,
        date=None,
        position_ref: str | None = None,
        operator_ref: str | None = None,
    ) -> CraftSummary:
        """
        Aggregate operational summary for a floor/date slice.

        This is a projection for dashboards and floor coordination, not a new
        domain state machine.
        """
        from shopman.craftsman.models import WorkOrder

        orders = cls._queue_queryset(
            date=date,
            position_ref=position_ref,
            operator_ref=operator_ref,
            statuses=[
                WorkOrder.Status.PLANNED,
                WorkOrder.Status.STARTED,
                WorkOrder.Status.FINISHED,
                WorkOrder.Status.VOID,
            ],
        )

        summary = CraftSummary()
        for order in orders:
            summary.total_orders += 1
            summary.planned_qty += order.quantity or Decimal("0")

            if order.status == WorkOrder.Status.PLANNED:
                summary.planned_orders += 1
            elif order.status == WorkOrder.Status.STARTED:
                summary.started_orders += 1
            elif order.status == WorkOrder.Status.FINISHED:
                summary.finished_orders += 1
            elif order.status == WorkOrder.Status.VOID:
                summary.void_orders += 1

            started_qty = _started_qty(order)
            if started_qty is not None:
                summary.started_qty += started_qty

            if order.finished is not None:
                summary.finished_qty += order.finished
                base_qty = started_qty or order.quantity
                summary.loss_qty += max(base_qty - order.finished, Decimal("0"))

        return summary

    @classmethod
    def _queue_queryset(
        cls,
        *,
        date=None,
        position_ref: str | None = None,
        operator_ref: str | None = None,
        statuses: list[str] | None = None,
    ):
        from shopman.craftsman.models import WorkOrder

        qs = (
            WorkOrder.objects.filter(status__in=statuses or [])
            .select_related("recipe")
            .prefetch_related("events")
            .order_by("target_date", "position_ref", "status", "created_at")
        )
        if date is not None:
            qs = qs.filter(target_date=date)
        if position_ref:
            qs = qs.filter(position_ref=position_ref)
        if operator_ref:
            qs = qs.filter(operator_ref=operator_ref)
        return qs


def _aggregate(agg, item_ref, quantity, unit):
    """Aggregate material need by (item_ref, unit)."""
    from shopman.craftsman.services.recipes import has_active_recipe_for_output_sku

    key = (item_ref, unit)
    if key in agg:
        agg[key].quantity += quantity
    else:
        has_recipe = has_active_recipe_for_output_sku(item_ref)
        agg[key] = Need(item_ref=item_ref, quantity=quantity, unit=unit, has_recipe=has_recipe)


def _started_qty(order) -> Decimal | None:
    """Resolve latest started quantity from prefetched events when available."""
    events = list(getattr(order, "_prefetched_objects_cache", {}).get("events", []))
    if not events:
        event = order.events.filter(kind="started").order_by("-seq").only("payload").first()
        if not event:
            return None
        return Decimal(str(event.payload.get("quantity", "0")))

    started_events = [event for event in events if event.kind == "started"]
    if not started_events:
        return None
    latest = max(started_events, key=lambda ev: ev.seq)
    return Decimal(str(latest.payload.get("quantity", "0")))


def _expand_bom(item_ref, quantity, unit, depth=0):
    """
    Recursively expand BOM to raw materials.

    If item_ref has an active Recipe, expand its items.
    Otherwise, yield as-is (terminal ingredient).

    Max depth 5 for cycle protection.
    """
    from shopman.craftsman.exceptions import CraftError
    from shopman.craftsman.services.recipes import get_active_recipe_for_output_sku

    if depth > 5:
        raise CraftError("BOM_CYCLE", item_ref=item_ref, depth=depth)

    sub_recipe = get_active_recipe_for_output_sku(item_ref)
    if sub_recipe:
        sub_coefficient = quantity / sub_recipe.batch_size
        for ri in sub_recipe.items.filter(is_optional=False).order_by("sort_order"):
            yield from _expand_bom(ri.input_sku, ri.quantity * sub_coefficient, ri.unit, depth + 1)
    else:
        yield (item_ref, quantity, unit)


def _calc_confidence(sample_size: int) -> str | None:
    """Return confidence label or None (skip) based on sample size."""
    if sample_size >= 8:
        return "high"
    if sample_size >= 3:
        return "medium"
    if sample_size >= 1:
        return "low"
    return None


_HOT_MONTHS = frozenset([10, 11, 12, 1, 2, 3])
_COLD_MONTHS = frozenset([6, 7, 8])
_MILD_MONTHS = frozenset([4, 5, 9])


def _season_label(months: list[int]) -> str | None:
    """Infer season label from a list of month ints."""
    m = frozenset(months)
    if m == _HOT_MONTHS:
        return "hot"
    if m == _COLD_MONTHS:
        return "cold"
    if m == _MILD_MONTHS:
        return "mild"
    return None


def _estimate_demand(dd):
    """
    Estimate true demand from a DailyDemand record.

    If soldout_at is None → demand = sold (full day of selling).
    If soldout_at is set → extrapolate based on selling rate, capped at 2x.
        rate = sold / minutes_selling
        estimated = min(rate * full_day_minutes, 2 * sold)

    Assumes bakery hours: 06:00 - 18:00 (720 minutes).
    """
    if dd.soldout_at is None:
        return dd.sold

    from datetime import date as date_type
    from datetime import datetime, time

    # Standard bakery hours
    open_time = time(6, 0)
    close_time = time(18, 0)
    dummy = date_type(2000, 1, 1)

    open_dt = datetime.combine(dummy, open_time)
    soldout_dt = datetime.combine(dummy, dd.soldout_at)
    close_dt = datetime.combine(dummy, close_time)

    minutes_selling = (soldout_dt - open_dt).total_seconds() / 60
    if minutes_selling <= 0:
        return dd.sold

    full_day_minutes = (close_dt - open_dt).total_seconds() / 60

    rate = dd.sold / Decimal(str(minutes_selling))
    estimated = rate * Decimal(str(full_day_minutes))

    # Cap at 2x actual sold to avoid wild overestimation
    cap = dd.sold * 2
    return min(estimated, cap)
