"""
Stockman Signal Handlers for Craftsman (vNext).

Listens to the single `production_changed` signal and dispatches
to appropriate Stockman actions:

- planned: Create planned Quant (future stock) for finished goods
- closed: No-op here (handled by InventoryProtocol in execution.py)
- voided: Cancel planned Quant for the WorkOrder

Registered by CraftsmanStockmanConfig.ready().
"""

from __future__ import annotations

import logging

from django.dispatch import receiver

from shopman.crafting.signals import production_changed

logger = logging.getLogger(__name__)


def _stockman_available() -> bool:
    """Check if Stockman is installed."""
    try:
        from shopman.stocking.services.movements import StockMovements  # noqa: F401

        return True
    except ImportError:
        return False


@receiver(production_changed)
def handle_production_changed(sender, product_ref, date, **kwargs):
    """
    React to production changes (plan, adjust, close, void).

    - planned: Create planned Quant in Stockman (future stock for finished goods)
    - adjusted: Update planned Quant quantity
    - closed: No-op (stock receive handled by InventoryProtocol)
    - voided: Cancel (zero out) the planned Quant
    """
    action = kwargs.get("action")
    work_order = kwargs.get("work_order")

    if not action:
        # Backward compat: signal without action kwarg — just log
        logger.info(
            "Production changed (no action): product_ref=%s date=%s",
            product_ref,
            date,
        )
        return

    if not _stockman_available():
        logger.debug(
            "Stockman not installed, skipping production_changed handler: "
            "action=%s product_ref=%s",
            action,
            product_ref,
        )
        return

    if action == "planned":
        _handle_planned(work_order, product_ref, date)
    elif action == "adjusted":
        _handle_adjusted(work_order, product_ref, date)
    elif action == "voided":
        _handle_voided(work_order, product_ref, date)
    elif action == "closed":
        _handle_closed(work_order, product_ref, date)
    else:
        logger.warning("Unknown production_changed action: %s", action)


def _resolve_position(ref: str):
    """Resolve a Position by ref string. Returns None if not found."""
    from shopman.stocking.models import Position

    if not ref:
        return None
    return Position.objects.filter(ref=ref).first()


def _handle_planned(work_order, product_ref, date):
    """Create a planned Quant for the finished goods output."""
    if not work_order or not date:
        logger.warning(
            "Cannot create planned quant: work_order=%s date=%s",
            work_order,
            date,
        )
        return

    from shopman.stocking.services.movements import StockMovements

    # Use WO.position_ref to determine position (string ref → Position.ref)
    position = _resolve_position(work_order.position_ref)

    try:
        StockMovements.receive(
            quantity=work_order.quantity,
            sku=product_ref,
            position=position,
            target_date=date,
            reason=f"Produção planejada: {work_order.code}",
        )
        logger.info(
            "Planned quant created: sku=%s qty=%s target_date=%s position=%s ref=%s",
            product_ref,
            work_order.quantity,
            date,
            work_order.position_ref or "(default)",
            work_order.code,
        )
    except Exception:
        logger.warning(
            "Failed to create planned quant for %s (non-fatal)",
            work_order.code,
            exc_info=True,
        )


def _handle_adjusted(work_order, product_ref, date):
    """
    Update the planned Quant to match the new WorkOrder quantity.

    Finds the existing planned Quant (by sku + target_date) and adjusts it.
    If no quant exists yet, creates one (defensive).
    """
    if not work_order or not date:
        logger.warning(
            "Cannot adjust planned quant: work_order=%s date=%s",
            work_order,
            date,
        )
        return

    from shopman.stocking.services.movements import StockMovements
    from shopman.stocking.services.queries import StockQueries

    try:
        quant = StockQueries.get_quant(product_ref, target_date=date)
        if quant is None:
            # Quant doesn't exist yet — create it (defensive)
            StockMovements.receive(
                quantity=work_order.quantity,
                sku=product_ref,
                target_date=date,
                reference=work_order.code,
                reason=f"Produção planejada (ajuste): {work_order.code}",
            )
        else:
            StockMovements.adjust(
                quant,
                work_order.quantity,
                reason=f"Ajuste WO {work_order.code}",
            )
        logger.info(
            "Planned quant adjusted: sku=%s qty=%s target_date=%s ref=%s",
            product_ref,
            work_order.quantity,
            date,
            work_order.code,
        )
    except Exception:
        logger.warning(
            "Failed to adjust planned quant for %s (non-fatal)",
            work_order.code,
            exc_info=True,
        )


def _handle_voided(work_order, product_ref, date):
    """
    Cancel the planned Quant by adjusting it to zero.

    Uses adjust(quant, 0) to remove the planned stock.
    """
    if not work_order:
        logger.warning("Cannot void planned quant: no work_order provided")
        return

    if not date:
        logger.info(
            "WorkOrder %s voided without scheduled_date — no planned quant to cancel",
            work_order.code,
        )
        return

    from shopman.stocking.services.movements import StockMovements
    from shopman.stocking.services.queries import StockQueries

    try:
        quant = StockQueries.get_quant(product_ref, target_date=date)
        if quant is None:
            logger.debug(
                "No planned quant found for sku=%s date=%s (already cancelled?)",
                product_ref,
                date,
            )
            return

        if quant.quantity > 0:
            StockMovements.adjust(
                quant,
                new_quantity=0,
                reason=f"WO cancelada: {work_order.code}",
            )
        logger.info(
            "Planned quant cancelled: sku=%s target_date=%s ref=%s",
            product_ref,
            date,
            work_order.code,
        )
    except Exception:
        logger.warning(
            "Failed to cancel planned quant for %s (non-fatal)",
            work_order.code,
            exc_info=True,
        )


def _handle_closed(work_order, product_ref, date):
    """
    Realize production: transfer planned stock → saleable position.

    Uses WO.position_ref to find the source (production) position.
    Moves to the first saleable position (vitrine).
    Holds are automatically migrated by stock.realize().
    """
    if not work_order or not date:
        logger.warning(
            "Cannot realize production: work_order=%s date=%s",
            work_order,
            date,
        )
        return

    from shopman.stocking.models import Position
    from shopman.stocking.services.planning import StockPlanning
    from shopman.stocking.services.queries import StockQueries

    produced = work_order.produced or work_order.quantity

    try:
        # Find saleable destination (vitrine)
        to_position = Position.objects.filter(is_saleable=True).first()
        if not to_position:
            logger.warning(
                "No saleable position found — cannot realize %s",
                work_order.code,
            )
            return

        # Find planned quant (may be at position_ref position or default)
        from_position = _resolve_position(work_order.position_ref)
        quant = StockQueries.get_quant(
            product_ref, target_date=date, position=from_position,
        )
        if quant is None:
            # Fallback: try without position filter
            quant = StockQueries.get_quant(product_ref, target_date=date)
        if quant is None:
            logger.info(
                "No planned quant for %s @ %s — nothing to realize",
                product_ref,
                date,
            )
            return

        StockPlanning.realize(
            product=type("P", (), {"sku": product_ref})(),
            target_date=date,
            actual_quantity=produced,
            to_position=to_position,
            from_position=from_position,
            reason=f"Produção concluída: {work_order.code}",
        )
        logger.info(
            "Production realized: sku=%s qty=%s %s → %s (WO %s)",
            product_ref,
            produced,
            work_order.position_ref or "(default)",
            to_position.ref,
            work_order.code,
        )
    except Exception:
        logger.warning(
            "Failed to realize production for %s (non-fatal)",
            work_order.code,
            exc_info=True,
        )
