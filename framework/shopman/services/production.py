"""
Production service — coordenação em torno do WorkOrder (WP-S5).

Reserva de insumos e movimentação física de estoque são integradas ao Core via
`production_changed` → contrib/stockman e InventoryProtocol no `craft.close()`.

Este módulo é o gancho explícito do orquestrador: logging estruturado e pontos
únicos para evoluir (alertas ao operador, integrações externas).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def reserve_materials(work_order) -> None:
    """Ponto de coordenação ao planejar produção.

    O Stockman reage ao signal `production_changed` (action=planned/adjusted).
    Aqui registramos o evento de domínio para auditoria e extensões futuras.
    """
    logger.info(
        "production.reserve_materials: wo=%s qty=%s ref=%s",
        work_order.ref,
        work_order.quantity,
        work_order.output_ref,
    )


def emit_goods(work_order) -> None:
    """Ponto de coordenação ao encerrar produção com saída real.

    Consumo de insumos e entrada do acabado ocorrem no `craft.close()` via
    InventoryProtocol quando configurado.
    """
    logger.info(
        "production.emit_goods: wo=%s produced=%s ref=%s",
        work_order.ref,
        work_order.produced,
        work_order.output_ref,
    )


def notify(work_order, event: str) -> None:
    """Notificação de lifecycle de produção (sem Order — apenas log por ora)."""
    logger.info(
        "production.notify: wo=%s event=%s",
        work_order.ref,
        event,
    )
