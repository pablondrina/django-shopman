"""
Production service — coordenação em torno do WorkOrder (WP-S5).

Reserva de insumos e movimentação física de estoque são integradas ao Core via
`production_changed` → contrib/stockman e InventoryProtocol no `craft.finish()`.

Este módulo é o gancho explícito do orquestrador: logging estruturado e pontos
únicos para evoluir (alertas ao operador, integrações externas).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BulkPlanResult:
    created: list[str]
    errors: list[str]
    target_date: date


def reserve_materials(work_order) -> None:
    """Ponto de coordenação ao planejar produção.

    O Stockman reage ao signal `production_changed` (action=planned/started).
    Aqui registramos o evento de domínio para auditoria e extensões futuras.
    """
    logger.info(
        "production.reserve_materials: wo=%s qty=%s ref=%s",
        work_order.ref,
        work_order.quantity,
        work_order.output_sku,
    )


def emit_goods(work_order) -> None:
    """Ponto de coordenação ao encerrar produção com saída real.

    Consumo de insumos e entrada do acabado ocorrem no `craft.finish()` via
    InventoryProtocol quando configurado.
    """
    logger.info(
        "production.emit_goods: wo=%s finished=%s ref=%s",
        work_order.ref,
        work_order.finished,
        work_order.output_sku,
    )


def notify(work_order, event: str) -> None:
    """Notificação de lifecycle de produção (sem Order — apenas log por ora)."""
    logger.info(
        "production.notify: wo=%s event=%s",
        work_order.ref,
        event,
    )


def void_work_order(
    work_order_id,
    *,
    actor: str,
    reason: str = "Estornado via produção rápida",
) -> str:
    """Void a work order and return its reference."""
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.execution import CraftExecution

    work_order = WorkOrder.objects.get(pk=work_order_id)
    CraftExecution.void(order=work_order, reason=reason, actor=actor)
    return work_order.ref


def quick_finish(
    *,
    recipe_id,
    quantity,
    position_id,
    actor: str,
) -> tuple[str, str, Decimal]:
    """Plan and immediately finish a production work order."""
    from shopman.craftsman.services.execution import CraftExecution
    from shopman.craftsman.services.scheduling import CraftPlanning

    recipe = _get_active_recipe(recipe_id)
    qty = _positive_decimal(quantity, error="Quantidade inválida.")
    position_ref = _position_ref(position_id)

    work_order = CraftPlanning.plan(
        recipe,
        qty,
        date=date.today(),
        position_ref=position_ref,
        source_ref="quick_production",
    )
    CraftExecution.finish(order=work_order, finished=qty, actor=actor)
    return recipe.output_sku, work_order.ref, qty


def set_planned_quantity(
    *,
    recipe_id,
    quantity,
    target_date_value,
    position_ref: str = "",
    operator_ref: str = "",
    actor: str,
) -> tuple[str, str, Decimal, str]:
    """Create or adjust the single planned WorkOrder behind a matrix cell."""
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.execution import CraftExecution
    from shopman.craftsman.services.scheduling import CraftPlanning

    recipe = _get_active_recipe(recipe_id)
    qty = _non_negative_decimal(quantity, error="Quantidade planejada inválida.")
    target_date = _target_date_or_today(target_date_value)
    position = str(position_ref or "").strip() or _default_position_ref()
    operator = str(operator_ref or "").strip()

    planned_orders = list(
        WorkOrder.objects.filter(
            recipe=recipe,
            target_date=target_date,
            position_ref=position,
            status=WorkOrder.Status.PLANNED,
        ).order_by("created_at")
    )

    if qty == 0:
        for work_order in planned_orders:
            CraftExecution.void(
                order=work_order,
                reason="Planejamento zerado na matriz",
                actor=actor,
            )
        return recipe.output_sku, "", qty, "cleared"

    if not planned_orders:
        work_order = CraftPlanning.plan(
            recipe,
            qty,
            date=target_date,
            position_ref=position,
            operator_ref=operator,
            source_ref="production_matrix",
            actor=actor,
        )
        return recipe.output_sku, work_order.ref, qty, "created"

    if len(planned_orders) > 1:
        raise ValueError(
            "Há mais de um planejamento aberto para este SKU. Ajuste a ordem específica antes de usar a matriz."
        )

    work_order = planned_orders[0]
    if work_order.quantity == qty:
        return recipe.output_sku, work_order.ref, qty, "unchanged"

    CraftPlanning.adjust(
        work_order,
        quantity=qty,
        reason="Planejamento informado na matriz",
        actor=actor,
    )
    return recipe.output_sku, work_order.ref, qty, "adjusted"


def start_work_order(
    *,
    work_order_id,
    quantity,
    position_id="",
    operator_ref: str = "",
    note: str = "",
    actor: str,
) -> tuple[str, Decimal]:
    """Mark a planned WorkOrder as started."""
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.scheduling import CraftPlanning

    qty = _positive_decimal(quantity, error="Quantidade iniciada inválida.")
    work_order = WorkOrder.objects.get(pk=work_order_id)
    position_ref = _position_ref(position_id) if position_id else work_order.position_ref
    operator = str(operator_ref or "").strip() or work_order.operator_ref
    CraftPlanning.start(
        work_order,
        quantity=qty,
        position_ref=position_ref,
        operator_ref=operator,
        note=str(note or "").strip(),
        actor=actor,
    )
    return work_order.ref, qty


def finish_work_order(
    *,
    work_order_id,
    quantity,
    actor: str,
) -> tuple[str, Decimal]:
    """Finish an existing WorkOrder with the actual produced quantity."""
    from shopman.craftsman.models import WorkOrder
    from shopman.craftsman.services.execution import CraftExecution

    qty = _positive_decimal(quantity, error="Quantidade concluída inválida.")
    work_order = WorkOrder.objects.get(pk=work_order_id)
    CraftExecution.finish(order=work_order, finished=qty, actor=actor)
    return work_order.ref, qty


def bulk_plan(
    *,
    target_date_value,
    entries: list[dict],
    source_ref: str = "dashboard_suggestion",
) -> BulkPlanResult:
    """Create planned work orders from suggestion entries."""
    from shopman.craftsman.models import Recipe
    from shopman.craftsman.services.scheduling import CraftPlanning

    target_date = _target_date(target_date_value)
    position_ref = _default_position_ref()
    created: list[str] = []
    errors: list[str] = []

    for entry in entries:
        recipe_ref = entry.get("recipe_ref", "")
        try:
            qty = _positive_decimal(entry.get("quantity", 0))
        except ValueError:
            errors.append(f"{recipe_ref}: quantidade inválida")
            continue

        try:
            recipe = Recipe.objects.get(ref=recipe_ref, is_active=True)
        except Recipe.DoesNotExist:
            errors.append(f"{recipe_ref}: receita não encontrada")
            continue

        try:
            work_order = CraftPlanning.plan(
                recipe,
                qty,
                date=target_date,
                position_ref=position_ref,
                source_ref=source_ref,
            )
            created.append(f"{recipe.output_sku} × {qty} ({work_order.ref})")
        except Exception as exc:
            errors.append(f"{recipe_ref}: {exc}")
            logger.exception("bulk_plan failed for %s", recipe_ref)

    return BulkPlanResult(created=created, errors=errors, target_date=target_date)


def _get_active_recipe(recipe_id):
    from shopman.craftsman.models import Recipe

    try:
        return Recipe.objects.get(pk=recipe_id, is_active=True)
    except (Recipe.DoesNotExist, ValueError, TypeError) as exc:
        raise ValueError("Receita inválida.") from exc


def _positive_decimal(value, *, error: str = "quantidade inválida") -> Decimal:
    try:
        qty = Decimal(str(value).strip())
        if qty <= 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(error) from exc
    return qty


def _non_negative_decimal(value, *, error: str = "quantidade inválida") -> Decimal:
    try:
        qty = Decimal(str(value).strip())
        if qty < 0:
            raise ValueError
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(error) from exc
    return qty


def _position_ref(position_id) -> str:
    if position_id:
        from shopman.stockman import Position

        try:
            return Position.objects.get(pk=position_id).ref
        except Position.DoesNotExist:
            pass
    return _default_position_ref()


def _default_position_ref() -> str:
    from shopman.stockman import Position

    default_pos = Position.objects.filter(is_default=True).first()
    return default_pos.ref if default_pos else ""


def _target_date(value) -> date:
    try:
        return date.fromisoformat(value) if value else date.today() + timedelta(days=1)
    except (ValueError, TypeError):
        return date.today() + timedelta(days=1)


def _target_date_or_today(value) -> date:
    try:
        return date.fromisoformat(value) if value else date.today()
    except (ValueError, TypeError):
        return date.today()
