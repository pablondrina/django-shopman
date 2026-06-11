"""Backstage runtime views: alerts, KDS, and production KDS.

The POS operator surface migrated to Nuxt/UI-Thing (surfaces/pos-uithing-nuxt,
served via the canonical api/v1/backstage/pos/* endpoints); the old POS-HTMX
view layer was removed (SURFACE-CONVERGENCE-PLAN WP1).
"""

from .alerts import alert_ack, alerts_badge, alerts_panel
from .kds_customer import kds_customer_board_orders_view, kds_customer_board_view
from .kds_station import (
    kds_station_picker_view,
    kds_station_runtime_cards_view,
    kds_station_runtime_check_view,
    kds_station_runtime_done_view,
    kds_station_runtime_expedition_view,
    kds_station_runtime_view,
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
    "kds_station_picker_view",
    "kds_station_runtime_cards_view",
    "kds_station_runtime_check_view",
    "kds_station_runtime_done_view",
    "kds_station_runtime_expedition_view",
    "kds_station_runtime_view",
    "production_advance_step_view",
    "production_kds_cards_view",
    "production_kds_finish_view",
    "production_kds_view",
]
