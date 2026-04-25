"""Production lifecycle coordination for WorkOrders.

Signal ``production_changed`` maps Craftsman actions to explicit lifecycle
phases. Recipes may select a lifecycle variant through
``Recipe.meta["production_lifecycle"]``; the dispatcher remains table-driven,
without lifecycle classes, inheritance, or registries.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from shopman.shop.services import production as production_svc

logger = logging.getLogger(__name__)

ProductionHandler = Callable[[object], None]


def production_lifecycle_name_for(recipe) -> str:
    """Resolve the production lifecycle name from Recipe.meta."""
    meta = recipe.meta or {}
    raw = meta.get("production_lifecycle")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return "standard"


def _action_to_phase(action: str) -> str | None:
    if action == "planned":
        return "on_planned"
    if action == "started":
        return "on_started"
    if action == "finished":
        return "on_finished"
    if action == "voided":
        return "on_voided"
    return None


def dispatch_production(work_order, phase: str) -> None:
    """Resolve recipe lifecycle and run the handler for the given phase."""
    if not phase:
        return

    lifecycle_name = production_lifecycle_name_for(work_order.recipe)
    handlers = _PRODUCTION_PHASE_HANDLERS.get(lifecycle_name)
    if handlers is None:
        logger.warning(
            "production_lifecycle.dispatch: unknown lifecycle=%s; using standard",
            lifecycle_name,
        )
        handlers = _PRODUCTION_PHASE_HANDLERS["standard"]

    handler = handlers.get(phase)
    if handler is None:
        logger.warning(
            "production_lifecycle.dispatch: no phase %s on lifecycle=%s",
            phase,
            lifecycle_name,
        )
        return

    handler(work_order)


def on_production_changed_receiver(sender, product_ref, date, **kwargs):
    """Receiver for ``production_changed``: map action to lifecycle phase."""
    work_order = kwargs.get("work_order")
    action = kwargs.get("action")
    if not work_order or not action:
        return

    phase = _action_to_phase(action)
    if phase:
        dispatch_production(work_order, phase)


def _standard_on_planned(work_order) -> None:
    production_svc.reserve_materials(work_order)
    production_svc.notify(work_order, "planned")


def _standard_on_started(work_order) -> None:
    production_svc.notify(work_order, "started")


def _standard_on_finished(work_order) -> None:
    production_svc.emit_goods(work_order)
    production_svc.notify(work_order, "finished")


def _standard_on_voided(work_order) -> None:
    production_svc.notify(work_order, "voided")


def _forecast_on_finished(work_order) -> None:
    _standard_on_finished(work_order)
    logger.info("production_lifecycle.forecast: finished wo=%s", work_order.ref)


def _subcontract_on_planned(work_order) -> None:
    production_svc.reserve_materials(work_order)
    production_svc.notify(work_order, "subcontract_planned")


def _subcontract_on_started(work_order) -> None:
    production_svc.notify(work_order, "subcontract_in_progress")


def _subcontract_on_finished(work_order) -> None:
    production_svc.emit_goods(work_order)
    production_svc.notify(work_order, "subcontract_finished")


def _subcontract_on_voided(work_order) -> None:
    production_svc.notify(work_order, "subcontract_voided")


_STANDARD_HANDLERS: dict[str, ProductionHandler] = {
    "on_planned": _standard_on_planned,
    "on_started": _standard_on_started,
    "on_finished": _standard_on_finished,
    "on_voided": _standard_on_voided,
}

_PRODUCTION_PHASE_HANDLERS: dict[str, dict[str, ProductionHandler]] = {
    "standard": _STANDARD_HANDLERS,
    "forecast": {
        **_STANDARD_HANDLERS,
        "on_finished": _forecast_on_finished,
    },
    "subcontract": {
        "on_planned": _subcontract_on_planned,
        "on_started": _subcontract_on_started,
        "on_finished": _subcontract_on_finished,
        "on_voided": _subcontract_on_voided,
    },
}
