"""Production operator command facade.

Backstage views call this module for production mutations. Domain invariants
remain in ``shopman.shop.services.production`` and Craftsman; this layer is the
operator-surface boundary for form-oriented actions.
"""

from __future__ import annotations

import logging
import csv
from io import StringIO
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone

from shopman.backstage.services.exceptions import ProductionError
from shopman.shop.services.production import BulkPlanResult
from shopman.shop.services import production as production_core

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MissingMaterial:
    sku: str
    needed: Decimal
    available: Decimal

    @property
    def shortage(self) -> Decimal:
        return max(Decimal("0"), self.needed - self.available)


class ProductionStockShortError(ProductionError):
    """Raised when pre-finish material validation detects a shortage."""

    def __init__(self, *, work_order_ref: str, missing: list[MissingMaterial]):
        self.work_order_ref = work_order_ref
        self.missing = missing
        summary = ", ".join(
            f"{item.sku}: faltam {_qty(item.shortage)}" for item in missing
        )
        super().__init__(f"Insumos insuficientes para {work_order_ref}: {summary}")


class ProductionOrderShortError(ProductionError):
    """Raised when a planned quantity no longer covers linked orders."""

    def __init__(self, *, work_order_ref: str, required: Decimal, requested: Decimal, order_refs: tuple[str, ...]):
        self.work_order_ref = work_order_ref
        self.required = required
        self.requested = requested
        self.order_refs = order_refs
        short = max(Decimal("0"), required - requested)
        super().__init__(
            f"{work_order_ref} supre {len(order_refs)} pedido(s); "
            f"precisa {_qty(required)} e a nova quantidade deixa {_qty(short)} descoberto."
        )


def apply_void(
    work_order_id,
    *,
    actor: str,
    reason: str = "Estornado via produção rápida",
) -> str:
    """Void a work order from the operator surface."""
    return production_core.void_work_order(
        work_order_id,
        actor=actor,
        reason=reason,
    )


def apply_quick_finish(
    *,
    recipe_id,
    quantity,
    position_id,
    actor: str,
):
    """Plan and immediately finish a work order from the operator surface."""
    return production_core.quick_finish(
        recipe_id=recipe_id,
        quantity=quantity,
        position_id=position_id,
        actor=actor,
    )


def apply_planned(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str = "",
    operator_ref: str = "",
    actor: str,
    force: bool = False,
):
    """Create or adjust the planned work order represented by a matrix cell."""
    _check_linked_order_coverage(
        recipe_id=recipe_id,
        quantity=quantity,
        target_date_value=target_date_value,
        position_ref=position_ref,
        operator_ref=operator_ref,
        force=force,
    )
    return production_core.set_planned_quantity(
        recipe_id=recipe_id,
        quantity=quantity,
        target_date_value=target_date_value,
        position_ref=position_ref,
        operator_ref=operator_ref,
        actor=actor,
    )


def apply_start(
    *,
    work_order_id,
    quantity,
    position_id="",
    operator_ref: str = "",
    note: str = "",
    actor: str,
):
    """Start a planned work order from the operator surface."""
    return production_core.start_work_order(
        work_order_id=work_order_id,
        quantity=quantity,
        position_id=position_id,
        operator_ref=operator_ref,
        note=note,
        actor=actor,
    )


def apply_finish(
    *,
    work_order_id,
    quantity,
    actor: str,
    force: bool = False,
):
    """Finish a work order from the operator surface."""
    work_order = _get_work_order(work_order_id)
    missing = check_finish_materials(work_order)
    if missing and not force:
        raise ProductionStockShortError(work_order_ref=work_order.ref, missing=missing)
    if missing:
        _create_stock_short_alert(
            work_order_id=work_order.pk,
            error=_missing_summary(missing),
        )

    try:
        result = production_core.finish_work_order(
            work_order_id=work_order_id,
            quantity=quantity,
            actor=actor,
        )
    except Exception as exc:
        if _looks_like_stock_error(exc):
            _create_stock_short_alert(work_order_id=work_order_id, error=str(exc))
        raise
    _record_batch_traceability(work_order_id=work_order_id, quantity=quantity)
    return result


def apply_advance_step(*, work_order_id, actor: str) -> int:
    """Advance the manual step pointer of a STARTED work order by one.

    Stores the new index in ``WorkOrder.meta["steps_progress"]`` (1-based).
    Returns the new step index. Capped at the number of recipe steps.
    Raises ProductionError if the work order is not in STARTED state or has
    no recipe steps.
    """
    from shopman.craftsman.models import WorkOrder

    work_order = _get_work_order(work_order_id)
    if work_order.status != WorkOrder.Status.STARTED:
        raise ProductionError("Só é possível avançar passo em ordens iniciadas.")

    steps = (work_order.recipe.meta or {}).get("steps") or work_order.recipe.steps or []
    total = len(steps)
    if total <= 0:
        raise ProductionError("Receita sem passos configurados.")

    meta = dict(work_order.meta or {})
    current = meta.get("steps_progress")
    try:
        current_value = int(current) if current not in (None, "") else 0
    except (TypeError, ValueError):
        current_value = 0
    new_index = max(1, min(total, current_value + 1))
    meta["steps_progress"] = new_index
    meta["steps_progress_actor"] = actor
    meta["steps_progress_updated_at"] = timezone.now().isoformat()
    work_order.meta = meta
    work_order.save(update_fields=["meta", "updated_at"])
    return new_index


def apply_suggestions(
    *,
    target_date_value,
    entries: list[dict],
) -> BulkPlanResult:
    """Create planned work orders from suggestion entries."""
    return production_core.bulk_plan(
        target_date_value=target_date_value,
        entries=entries,
    )


def export_reports_csv(report_kind: str, filters: dict | None = None) -> bytes:
    """Export a production report as UTF-8 BOM CSV for spreadsheet tools."""
    from shopman.backstage.projections.production import build_production_reports

    requested = dict(filters or {})
    requested["report_kind"] = report_kind
    reports = build_production_reports(requested)
    output = StringIO()
    writer = csv.writer(output)

    if reports.filters.report_kind == "operator_productivity":
        writer.writerow([
            "Operador",
            "Nome",
            "Ordens finalizadas",
            "Qtd total",
            "Yield médio",
            "Tempo médio (min)",
        ])
        for row in reports.operator_rows:
            writer.writerow([
                row.operator_ref,
                row.operator_name,
                row.wo_count,
                row.qty_total,
                row.yield_avg,
                row.duration_avg_minutes,
            ])
    elif reports.filters.report_kind == "recipe_waste":
        writer.writerow([
            "Receita",
            "Nome",
            "Ordens",
            "Perda total",
            "Yield médio",
            "Utilização capacidade",
        ])
        for row in reports.waste_rows:
            writer.writerow([
                row.recipe_ref,
                row.recipe_name,
                row.wo_count,
                row.loss_total,
                row.yield_avg,
                row.capacity_utilization,
            ])
    else:
        writer.writerow([
            "Ref",
            "Data",
            "Receita",
            "Nome da receita",
            "Posição",
            "Qtd planejada",
            "Qtd iniciada",
            "Qtd finalizada",
            "Perda",
            "Yield",
            "Operador",
            "Iniciada em",
            "Finalizada em",
            "Duração (min)",
        ])
        for row in reports.history_rows:
            writer.writerow([
                row.ref,
                row.date,
                row.recipe_ref,
                row.recipe_name,
                row.position_ref,
                row.qty_planned,
                row.qty_started,
                row.qty_finished,
                row.qty_loss,
                row.yield_rate,
                row.operator_ref,
                row.started_at,
                row.finished_at,
                row.duration_minutes,
            ])

    return ("\ufeff" + output.getvalue()).encode("utf-8")


def served_orders_for_work_order(wo_ref: str):
    """Return a work order and the orders referenced by its contextual sync metadata."""
    from shopman.craftsman.models import WorkOrder
    from shopman.orderman.models import Order

    work_order = WorkOrder.objects.select_related("recipe").get(ref=wo_ref)
    refs = tuple(dict.fromkeys((work_order.meta or {}).get("serves_order_refs") or ()))
    orders = tuple(
        Order.objects.filter(ref__in=refs)
        .prefetch_related("items")
        .order_by("created_at")
    )
    return work_order, refs, orders


def _check_linked_order_coverage(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str,
    operator_ref: str,
    force: bool,
) -> None:
    if force:
        return
    try:
        from shopman.craftsman.models import Recipe, WorkOrder
        from shopman.shop.handlers.production_order_sync import linked_order_refs, order_requirement_for_work_order

        recipe = Recipe.objects.get(pk=recipe_id)
        requested = Decimal(str(quantity or "0"))
        work_order = (
            WorkOrder.objects.filter(
                recipe=recipe,
                target_date=target_date_value,
                status=WorkOrder.Status.PLANNED,
                position_ref=position_ref or "",
                operator_ref=operator_ref or "",
            )
            .first()
        )
        if not work_order:
            return
        order_refs = linked_order_refs(work_order)
        if not order_refs:
            return
        required = order_requirement_for_work_order(work_order)
        if requested < required:
            raise ProductionOrderShortError(
                work_order_ref=work_order.ref,
                required=required,
                requested=requested,
                order_refs=order_refs,
            )
    except ProductionOrderShortError:
        raise
    except Exception:
        logger.debug("production_order_coverage_check_failed recipe_id=%s", recipe_id, exc_info=True)


def _looks_like_stock_error(exc: Exception) -> bool:
    lower = str(exc).lower()
    return any(token in lower for token in ("estoque", "stock", "insuficiente", "inventory"))


def _create_stock_short_alert(*, work_order_id, error: str) -> None:
    try:
        from shopman.shop.handlers.production_alerts import create_stock_short_alert

        work_order = _get_work_order(work_order_id)
        create_stock_short_alert(
            work_order_ref=work_order.ref,
            output_sku=work_order.output_sku,
            error=error,
        )
    except Exception:
        logger.warning("production_stock_short_alert_failed work_order_id=%s", work_order_id, exc_info=True)


def check_finish_materials(work_order) -> list[MissingMaterial]:
    """Validate materials needed to finish a specific WorkOrder."""
    backend_path = _craftsman_setting("INVENTORY_BACKEND")
    if not backend_path:
        return []

    material_needs = _material_needs_for_work_order(work_order)
    if not material_needs:
        return []

    try:
        from django.utils.module_loading import import_string

        result = import_string(backend_path)().available(material_needs)
    except Exception as exc:
        mode = _craftsman_setting("MODE")
        if mode == "strict":
            raise ProductionError(f"Falha ao consultar estoque de insumos: {exc}") from exc
        logger.warning("production_material_check_failed work_order=%s", work_order.ref, exc_info=True)
        return []

    return [
        MissingMaterial(
            sku=status.sku,
            needed=status.needed,
            available=status.available,
        )
        for status in result.materials
        if not status.sufficient
    ]


def _material_needs_for_work_order(work_order):
    from shopman.craftsman.protocols.inventory import MaterialNeed

    recipe = work_order.recipe
    started_qty = work_order.started_qty or work_order.quantity
    snapshot = (work_order.meta or {}).get("_recipe_snapshot")
    if snapshot:
        batch_size = Decimal(str(snapshot["batch_size"]))
        items = snapshot.get("items") or []
    else:
        batch_size = recipe.batch_size
        items = [
            {
                "input_sku": item.input_sku,
                "quantity": str(item.quantity),
                "unit": item.unit,
            }
            for item in recipe.items.filter(is_optional=False).order_by("sort_order")
        ]

    coefficient = started_qty / batch_size
    return [
        MaterialNeed(
            sku=item["input_sku"],
            quantity=Decimal(str(item["quantity"])) * coefficient,
            unit=item.get("unit", "un"),
            position_ref=work_order.position_ref or None,
        )
        for item in items
    ]


def _record_batch_traceability(*, work_order_id, quantity) -> None:
    work_order = _get_work_order(work_order_id)
    meta = work_order.recipe.meta or {}
    if not meta.get("requires_batch_tracking"):
        return

    try:
        from shopman.stockman.models import Batch

        production_date = work_order.target_date or timezone.localdate()
        shelf_life_days = meta.get("shelf_life_days")
        expiry_date = None
        if shelf_life_days not in (None, ""):
            expiry_date = production_date + timedelta(days=int(shelf_life_days))

        batch_ref = f"{work_order.output_sku}-{production_date:%Y%m%d}-{work_order.pk}"
        Batch.objects.get_or_create(
            ref=batch_ref,
            defaults={
                "sku": work_order.output_sku,
                "production_date": production_date,
                "expiry_date": expiry_date,
                "notes": f"Produção {work_order.ref}",
            },
        )
        work_order.meta = {
            **(work_order.meta or {}),
            "batch_ref": batch_ref,
            "batch_quantity": str(quantity),
            "expiry_date": expiry_date.isoformat() if expiry_date else "",
        }
        work_order.save(update_fields=["meta", "updated_at"])
    except Exception:
        logger.warning("production_batch_traceability_failed work_order_id=%s", work_order_id, exc_info=True)


def _get_work_order(work_order_id):
    from shopman.craftsman.models import WorkOrder

    return WorkOrder.objects.select_related("recipe").prefetch_related("recipe__items").get(pk=work_order_id)


def _craftsman_setting(name):
    from shopman.craftsman.conf import get_setting

    return get_setting(name)


def _missing_summary(missing: list[MissingMaterial]) -> str:
    return "; ".join(
        f"{item.sku} necessário {_qty(item.needed)}, disponível {_qty(item.available)}"
        for item in missing
    )


def _qty(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.001")).normalize())
