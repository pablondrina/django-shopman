"""Backstage projections — typed read models for operator-facing surfaces."""

from .closing import (
    ClosingItemProjection,
    DayClosingProjection,
    build_day_closing,
)
from .dashboard import (
    DashboardProjection,
    build_dashboard,
)
from .kds import (
    KDSBoardProjection,
    KDSExpeditionCardProjection,
    KDSInstanceSummaryProjection,
    KDSItemProjection,
    KDSTicketProjection,
    build_kds_board,
    build_kds_index,
    build_kds_ticket,
)
from .order_queue import (
    OperatorOrderProjection,
    OrderCardProjection,
    OrderQueueProjection,
    TwoZoneQueueProjection,
    build_operator_order,
    build_order_card,
    build_order_queue,
    build_two_zone_queue,
)
from .pos import (
    POSProjection,
    POSShiftSummaryProjection,
    build_pos,
    build_pos_shift_summary,
)
from .production import (
    ProductionBoardProjection,
    ProductionCountsProjection,
    WorkOrderCardProjection,
    build_production_board,
)

__all__ = [
    "ClosingItemProjection",
    "DashboardProjection",
    "DayClosingProjection",
    "KDSBoardProjection",
    "KDSExpeditionCardProjection",
    "KDSInstanceSummaryProjection",
    "KDSItemProjection",
    "KDSTicketProjection",
    "OperatorOrderProjection",
    "OrderCardProjection",
    "OrderQueueProjection",
    "TwoZoneQueueProjection",
    "POSProjection",
    "POSShiftSummaryProjection",
    "ProductionBoardProjection",
    "ProductionCountsProjection",
    "WorkOrderCardProjection",
    "build_dashboard",
    "build_day_closing",
    "build_kds_board",
    "build_kds_index",
    "build_kds_ticket",
    "build_operator_order",
    "build_order_card",
    "build_order_queue",
    "build_two_zone_queue",
    "build_pos",
    "build_pos_shift_summary",
    "build_production_board",
]
