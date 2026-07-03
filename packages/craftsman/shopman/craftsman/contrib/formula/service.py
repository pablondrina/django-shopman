from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any

from django.db import models, transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from shopman.craftsman.conf import get_setting
from shopman.craftsman.exceptions import CraftError
from shopman.craftsman.protocols.inventory import MaterialNeed
from shopman.craftsman.service import craft

logger = logging.getLogger(__name__)


class FormulaAvailabilityError(CraftError):
    """Raised when a suggestion has material shortages without override."""

    def __init__(self, shortages: list[dict[str, str]], *, message: str | None = None):
        super().__init__(
            "FORMULA_INSUFFICIENT_MATERIALS",
            message=message or "Insumos insuficientes para aceitar a sugestao.",
            shortages=shortages,
        )


@dataclass(frozen=True)
class FormulaSuggestionLine:
    """Ephemeral formula suggestion line."""

    recipe: object
    quantity: Decimal
    base_quantity: Decimal
    adjusted_quantity: Decimal
    rounded_quantity: Decimal
    basis: dict[str, Any] = field(default_factory=dict)


def suggest(
    target_date: date,
    output_skus: list[str] | tuple[str, ...] | None = None,
    *,
    season_months: list[int] | None = None,
    high_demand_multiplier: Decimal | None = None,
    safety_pct: Decimal | None = None,
) -> list[FormulaSuggestionLine]:
    """Build ephemeral formula suggestions from craft.suggest()."""
    base_suggestions = craft.suggest(
        target_date,
        output_skus=output_skus,
        season_months=season_months,
        high_demand_multiplier=high_demand_multiplier,
        safety_pct=safety_pct,
    )
    return [_build_line(suggestion, target_date=target_date) for suggestion in base_suggestions]


def accept_suggestion(
    *,
    recipe_ref: str,
    target_date: date,
    quantity: Decimal | str | int | None = None,
    actor: str = "",
    position_ref: str = "",
    operator_ref: str = "",
    allow_shortage: bool = False,
    override_reason: str = "",
    basis: dict[str, Any] | None = None,
):
    """Accept a formula suggestion by creating a WorkOrder."""
    from shopman.craftsman.models import Recipe, WorkOrderEvent

    recipe = Recipe.objects.get(ref=recipe_ref, is_active=True)
    if basis is None:
        line = _line_for_recipe(recipe=recipe, target_date=target_date)
        if line is None:
            raise CraftError("FORMULA_SUGGESTION_NOT_FOUND", recipe_ref=recipe_ref)
        planned_qty = _decimal(quantity) if quantity is not None else line.quantity
        formula_basis = _basis_with_quantity(line.basis, planned_qty)
    else:
        planned_qty = _decimal(quantity) if quantity is not None else _decimal(
            basis.get("rounded_quantity") or basis.get("adjusted_quantity") or basis.get("base_quantity")
        )
        formula_basis = _basis_with_quantity(basis, planned_qty)

    availability = formula_basis.get("material_availability") or {}
    shortages = list(availability.get("shortages") or [])
    if availability.get("all_available") is False and shortages and not allow_shortage:
        raise FormulaAvailabilityError(shortages)

    if allow_shortage:
        formula_basis["availability_override"] = {
            "reason": override_reason,
            "actor": actor,
            "accepted_at": timezone.now().isoformat(),
        }

    meta = {
        "formula_basis": formula_basis,
    }
    with transaction.atomic():
        work_order = craft.plan(
            recipe,
            planned_qty,
            date=target_date,
            source_ref="formula:suggestion",
            position_ref=position_ref,
            operator_ref=operator_ref,
            actor=actor,
            meta=meta,
        )
        WorkOrderEvent.objects.create(
            work_order=work_order,
            seq=_next_seq(work_order),
            kind=WorkOrderEvent.Kind.ADJUSTED,
            payload={
                "reason": "formula_accept",
                "quantity": str(planned_qty),
                "formula_basis": formula_basis,
                "availability_override": bool(allow_shortage),
            },
            actor=actor,
        )
    return work_order


def _line_for_recipe(*, recipe, target_date: date) -> FormulaSuggestionLine | None:
    for line in suggest(target_date, output_skus=[recipe.output_sku]):
        if line.recipe.pk == recipe.pk:
            return line
    return None


def _build_line(suggestion, *, target_date: date) -> FormulaSuggestionLine:
    recipe = suggestion.recipe
    base_quantity = _decimal(suggestion.quantity)
    factors = _factor_dicts(
        recipe=recipe,
        target_date=target_date,
        base_basis=dict(suggestion.basis or {}),
    )
    adjusted = _apply_factors(base_quantity, factors)
    rounded = _round_quantity(adjusted)
    availability = _material_availability(recipe=recipe, quantity=rounded)
    basis = _json_basis({
        **dict(suggestion.basis or {}),
        "date": target_date.isoformat(),
        "output_sku": recipe.output_sku,
        "recipe_ref": recipe.ref,
        "base_quantity": base_quantity,
        "adjusted_quantity": adjusted,
        "rounded_quantity": rounded,
        "factors": factors,
        "material_availability": availability,
    })
    return FormulaSuggestionLine(
        recipe=recipe,
        quantity=rounded,
        base_quantity=base_quantity,
        adjusted_quantity=adjusted,
        rounded_quantity=rounded,
        basis=basis,
    )


def _factor_dicts(*, recipe, target_date: date, base_basis: dict[str, Any]) -> list[dict[str, Any]]:
    factors: list[dict[str, Any]] = []
    for provider_path in get_setting("FORMULA_FACTOR_PROVIDERS") or []:
        try:
            provider = import_string(provider_path)()
            provided = provider.factors_for(
                date=target_date,
                output_sku=recipe.output_sku,
                recipe=recipe,
                base_basis=base_basis,
            )
            factors.extend(dict(item) for item in (provided or []))
        except Exception:
            logger.warning("formula_factor_provider_failed provider=%s", provider_path, exc_info=True)

    capacity_provider_path = get_setting("FORMULA_CAPACITY_PROVIDER")
    if capacity_provider_path:
        try:
            provider = import_string(capacity_provider_path)()
            capacity = provider.capacity_for(date=target_date, output_sku=recipe.output_sku, recipe=recipe)
            if capacity and capacity.get("max_quantity") not in (None, ""):
                factors.append({
                    "ref": capacity.get("ref", "capacity"),
                    "kind": "cap",
                    "value": str(capacity["max_quantity"]),
                    "reason": capacity.get("reason", "capacity"),
                    "source": capacity_provider_path,
                    "version": str(capacity.get("version") or target_date),
                })
        except Exception:
            logger.warning("formula_capacity_provider_failed provider=%s", capacity_provider_path, exc_info=True)
    return [_json_basis(factor) for factor in factors]


def _apply_factors(quantity: Decimal, factors: list[dict[str, Any]]) -> Decimal:
    result = quantity
    for factor in factors:
        kind = str(factor.get("kind") or "").strip().lower()
        value = _decimal(factor.get("value", "0"))
        if kind == "multiplier":
            result *= value
        elif kind in {"add", "additive"}:
            result += value
        elif kind == "floor":
            result = max(result, value)
        elif kind in {"cap", "capacity"}:
            result = min(result, value)
    return max(result, Decimal("0"))


def _round_quantity(quantity: Decimal) -> Decimal:
    multiple = get_setting("FORMULA_ROUNDING_MULTIPLE")
    if multiple in (None, "", 0, "0"):
        return quantity.quantize(Decimal("0.001")).normalize()
    step = _decimal(multiple)
    if step <= 0:
        return quantity.quantize(Decimal("0.001")).normalize()
    rounded_steps = (quantity / step).to_integral_value(rounding=ROUND_CEILING)
    return (rounded_steps * step).quantize(Decimal("0.001")).normalize()


def _material_availability(*, recipe, quantity: Decimal) -> dict[str, Any]:
    # Ingredient-availability status for the suggestion. Active when
    # INVENTORY_BACKEND is configured (Buyman WP-B5b); status="unknown" otherwise.
    backend_path = get_setting("INVENTORY_BACKEND")
    needs = _material_needs(recipe=recipe, quantity=quantity)
    if not needs:
        return {"all_available": True, "shortages": [], "status": "available"}
    if not backend_path:
        return {"all_available": None, "shortages": [], "status": "unknown"}
    try:
        backend = import_string(backend_path)()
        result = backend.available(needs)
        shortages = [
            {
                "sku": status.sku,
                "needed": str(status.needed),
                "available": str(status.available),
                "shortage": str(status.shortage),
            }
            for status in result.materials
            if not status.sufficient
        ]
        return {
            "all_available": bool(result.all_available),
            "shortages": shortages,
            "status": "available" if result.all_available else "short",
        }
    except Exception:
        logger.warning("formula_material_availability_failed recipe=%s", recipe.ref, exc_info=True)
        return {"all_available": None, "shortages": [], "status": "unknown"}


def _material_needs(*, recipe, quantity: Decimal) -> list[MaterialNeed]:
    if not recipe.batch_size:
        return []
    coefficient = quantity / recipe.batch_size
    return [
        MaterialNeed(
            sku=item.input_sku,
            quantity=(item.quantity * coefficient).quantize(Decimal("0.001")).normalize(),
            unit=item.unit,
        )
        for item in recipe.items.filter(is_optional=False).order_by("sort_order")
    ]


def _basis_with_quantity(basis: dict[str, Any], quantity: Decimal) -> dict[str, Any]:
    data = _json_basis(dict(basis or {}))
    data["accepted_quantity"] = str(quantity)
    return data


def _json_basis(value):
    if isinstance(value, dict):
        return {str(k): _json_basis(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_basis(v) for v in value]
    if isinstance(value, tuple):
        return [_json_basis(v) for v in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _decimal(value) -> Decimal:
    try:
        return Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CraftError("INVALID_QUANTITY", quantity=value) from exc


def _next_seq(work_order) -> int:
    from django.db.models import Value
    from django.db.models.functions import Coalesce

    return (
        work_order.events.aggregate(m=Coalesce(models.Max("seq"), Value(-1)))["m"]
        + 1
    )
