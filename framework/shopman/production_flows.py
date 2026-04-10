"""
Production flow hierarchy — lifecycle coordination for WorkOrders (WP-S5).

Signal `production_changed` → dispatch_production() → Flow.on_<phase>() → services.

Phases (mapeamento a partir do Core):
    planned   → on_planned
    adjusted  → on_started (apenas no primeiro ajuste — início efetivo)
    closed    → on_closed
    voided    → on_voided

Configuração por receita: `Recipe.meta["production_flow"]` ∈
`standard` | `forecast` | `subcontract` (default: `standard`).
"""

from __future__ import annotations

import logging

from shopman.adapters import get_adapter
from shopman.services import production as production_svc

logger = logging.getLogger(__name__)

# ── Registry ─────────────────────────────────────────────────────────

_registry: dict[str, type[BaseProductionFlow]] = {}


def production_flow(name: str):
    """Decorator que registra uma ProductionFlow no registry."""

    def decorator(cls: type[BaseProductionFlow]) -> type[BaseProductionFlow]:
        _registry[name] = cls
        cls.flow_name = name  # type: ignore[attr-defined]
        return cls

    return decorator


def production_flow_name_for(recipe) -> str:
    """Resolve o nome do flow a partir de Recipe.meta (sem campo no Core)."""
    meta = recipe.meta or {}
    raw = meta.get("production_flow")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    return "standard"


def get_production_flow(recipe) -> BaseProductionFlow:
    """Instancia o flow configurado na receita (fallback: StandardFlow)."""
    key = production_flow_name_for(recipe)
    cls = _registry.get(key) or StandardFlow
    return cls()


def _action_to_phase(action: str, work_order) -> str | None:
    """Traduz action do signal Core → método on_* do flow."""
    if action == "planned":
        return "on_planned"
    if action == "adjusted":
        production = get_adapter("production")
        n = production.count_adjusted_events(work_order.ref)
        return "on_started" if n == 1 else None
    if action == "closed":
        return "on_closed"
    if action == "voided":
        return "on_voided"
    return None


def dispatch_production(work_order, phase: str) -> None:
    """Resolve Flow e chama o método da fase."""
    if not phase:
        return
    recipe = work_order.recipe
    flow = get_production_flow(recipe)
    method = getattr(flow, phase, None)
    if method is None:
        logger.warning(
            "production_flows.dispatch: no phase %s on %s",
            phase,
            type(flow).__name__,
        )
        return
    method(work_order)


def on_production_changed_receiver(sender, product_ref, date, **kwargs):
    """Receiver para `production_changed` — mapeia action → fase."""
    work_order = kwargs.get("work_order")
    action = kwargs.get("action")
    if not work_order or not action:
        return
    phase = _action_to_phase(action, work_order)
    if phase:
        dispatch_production(work_order, phase)


# ── BaseProductionFlow ────────────────────────────────────────────────


class BaseProductionFlow:
    """Ciclo: plan → start → close | void."""

    def on_planned(self, work_order):
        pass

    def on_started(self, work_order):
        pass

    def on_closed(self, work_order):
        pass

    def on_voided(self, work_order):
        pass


@production_flow("standard")
class StandardFlow(BaseProductionFlow):
    """Plano → produzir → fechar."""

    def on_planned(self, work_order):
        production_svc.reserve_materials(work_order)
        production_svc.notify(work_order, "planned")

    def on_started(self, work_order):
        production_svc.notify(work_order, "started")

    def on_closed(self, work_order):
        production_svc.emit_goods(work_order)
        production_svc.notify(work_order, "closed")

    def on_voided(self, work_order):
        production_svc.notify(work_order, "voided")


@production_flow("forecast")
class ForecastFlow(StandardFlow):
    """Previsão — mesmo pipeline que standard; fechamento pode ter política adicional."""

    def on_closed(self, work_order):
        super().on_closed(work_order)
        logger.info("ForecastFlow: closed wo=%s", work_order.ref)


@production_flow("subcontract")
class SubcontractFlow(BaseProductionFlow):
    """Terceirização — plano → envio → retorno → fechar (hooks distintos)."""

    def on_planned(self, work_order):
        production_svc.reserve_materials(work_order)
        production_svc.notify(work_order, "subcontract_planned")

    def on_started(self, work_order):
        production_svc.notify(work_order, "subcontract_in_progress")

    def on_closed(self, work_order):
        production_svc.emit_goods(work_order)
        production_svc.notify(work_order, "subcontract_closed")

    def on_voided(self, work_order):
        production_svc.notify(work_order, "subcontract_voided")
