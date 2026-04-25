"""Backstage views — operator-facing surfaces (KDS, POS, Gestor, Fechamento, Produção)."""

from .closing import closing_view
from .kds import (
    KDSDisplayView,
    KDSExpeditionActionView,
    KDSIndexView,
    KDSTicketCheckItemView,
    KDSTicketDoneView,
    KDSTicketListPartialView,
)
from .orders import (
    AlertAcknowledgeView,
    OperatorOrdersView,
    OrderAdvanceView,
    OrderConfirmView,
    OrderDetailPartialView,
    OrderHistoricoView,
    OrderListPartialView,
    OrderMarkPaidView,
    OrderNotesView,
    OrderRejectView,
)
from .pos import (
    pos_cancel_last,
    pos_cash_close,
    pos_cash_open,
    pos_cash_sangria,
    pos_close,
    pos_customer_lookup,
    pos_load_session,
    pos_park,
    pos_sessions,
    pos_shift_summary,
    pos_view,
)
from .production import bulk_create_work_orders

__all__ = [
    "closing_view",
    "KDSDisplayView",
    "KDSExpeditionActionView",
    "KDSIndexView",
    "KDSTicketCheckItemView",
    "KDSTicketDoneView",
    "KDSTicketListPartialView",
    "OperatorOrdersView",
    "OrderAdvanceView",
    "OrderConfirmView",
    "OrderDetailPartialView",
    "OrderHistoricoView",
    "OrderListPartialView",
    "OrderMarkPaidView",
    "OrderNotesView",
    "OrderRejectView",
    "AlertAcknowledgeView",
    "bulk_create_work_orders",
    "pos_cancel_last",
    "pos_cash_close",
    "pos_cash_open",
    "pos_cash_sangria",
    "pos_close",
    "pos_customer_lookup",
    "pos_load_session",
    "pos_park",
    "pos_sessions",
    "pos_shift_summary",
    "pos_view",
]
