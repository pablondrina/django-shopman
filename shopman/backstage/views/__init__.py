"""Backstage runtime views: alerts, POS, KDS, and production KDS."""

from .alerts import alert_ack, alerts_badge, alerts_panel
from .kds_customer import kds_customer_board_orders_view, kds_customer_board_view
from .kds_station import (
    kds_station_runtime_cards_view,
    kds_station_runtime_check_view,
    kds_station_runtime_done_view,
    kds_station_runtime_expedition_view,
    kds_station_runtime_view,
)
from .pos import (
    pos_cancel_last,
    pos_cash_close,
    pos_cash_open,
    pos_cash_sangria,
    pos_close,
    pos_customer_lookup,
    pos_shift_summary,
    pos_tab_clear,
    pos_tab_create,
    pos_tab_open,
    pos_tab_save,
    pos_tabs,
    pos_view,
)
from .production import (
    production_advance_step_view,
    production_kds_cards_view,
    production_kds_finish_view,
    production_kds_view,
)

__all__ = [
    "alert_ack",
    "alerts_badge",
    "alerts_panel",
    "kds_customer_board_orders_view",
    "kds_customer_board_view",
    "kds_station_runtime_cards_view",
    "kds_station_runtime_check_view",
    "kds_station_runtime_done_view",
    "kds_station_runtime_expedition_view",
    "kds_station_runtime_view",
    "production_advance_step_view",
    "production_kds_cards_view",
    "production_kds_finish_view",
    "production_kds_view",
    "pos_cancel_last",
    "pos_cash_close",
    "pos_cash_open",
    "pos_cash_sangria",
    "pos_close",
    "pos_customer_lookup",
    "pos_shift_summary",
    "pos_tab_clear",
    "pos_tab_create",
    "pos_tab_open",
    "pos_tab_save",
    "pos_tabs",
    "pos_view",
]
