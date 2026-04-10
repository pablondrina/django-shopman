"""
Orderman Holds — Utilitários compartilhados para liberação de holds de estoque.

Usado por handlers de confirmation e payment quando precisam liberar holds
após cancelamento de pedido (timeout, rejeição, etc).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def release_holds_for_order(order: Any) -> None:
    """
    Libera todos os holds de estoque associados a um pedido.

    Busca hold_ids em order.data["holds"] e libera cada um via
    StockBackend obtido do registry.

    Silencia exceções por hold individual para garantir que falha
    em um hold não impeça a liberação dos demais.
    """
    from shopman.orderman.registry import get_directive_handler

    holds = getattr(order, "data", {}).get("holds", [])
    if not holds:
        return

    handler = get_directive_handler("stock.hold")
    if not handler or not hasattr(handler, "backend"):
        logger.warning(
            "release_holds_for_order: stock.hold handler not found in registry. "
            "Cannot release holds for order %s.",
            getattr(order, "ref", "?"),
        )
        return

    backend = handler.backend
    released = 0
    for hold in holds:
        hold_id = hold.get("hold_id")
        if not hold_id:
            continue
        try:
            backend.release_hold(hold_id)
            released += 1
        except Exception:
            logger.exception(
                "release_holds_for_order: failed to release hold %s for order %s",
                hold_id,
                getattr(order, "ref", "?"),
            )

    if released:
        logger.info(
            "release_holds_for_order: released %d/%d holds for order %s.",
            released,
            len(holds),
            getattr(order, "ref", "?"),
        )
