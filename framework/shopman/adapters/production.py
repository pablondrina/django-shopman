"""
Internal production adapter — delegates to Craftsman (Core).

Core: WorkOrder, WorkOrderEvent, Recipe
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def get_work_order(code: str) -> dict | None:
    """Retorna {"code", "quantity", "output_ref", "produced", "recipe_name"} ou None."""
    try:
        from shopman.craftsman.models import WorkOrder

        wo = WorkOrder.objects.select_related("recipe").get(code=code)
        return {
            "code": wo.code,
            "quantity": wo.quantity,
            "output_ref": wo.output_ref,
            "produced": wo.produced,
            "recipe_name": wo.recipe.name if wo.recipe else "",
        }
    except Exception:
        return None


def count_adjusted_events(work_order_code: str) -> int:
    """Conta eventos ADJUSTED de uma work order."""
    from shopman.craftsman.models import WorkOrderEvent

    return WorkOrderEvent.objects.filter(
        work_order__code=work_order_code,
        kind=WorkOrderEvent.Kind.ADJUSTED,
    ).count()


def get_prep_skus(skus: list[str]) -> set[str]:
    """Retorna o conjunto de SKUs que têm receitas ativas (necessitam preparo no KDS)."""
    try:
        from shopman.craftsman.models import Recipe

        return set(
            Recipe.objects.filter(output_ref__in=skus, is_active=True)
            .values_list("output_ref", flat=True)
        )
    except ImportError:
        return set()


def get_finished_work_orders(skus: list[str], cutoff_date) -> list[tuple]:
    """Retorna [(output_ref, finished_at)] de WorkOrders concluídas no período."""
    from shopman.craftsman.models import WorkOrder

    return list(
        WorkOrder.objects.filter(
            output_ref__in=skus,
            status="done",
            finished_at__isnull=False,
            finished_at__date__gte=cutoff_date,
        ).values_list("output_ref", "finished_at")
    )
