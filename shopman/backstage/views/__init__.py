"""Backstage runtime views: production KDS.

The operator surfaces migrated to dedicated Nuxt/UI-Thing apps served via the
canonical ``api/v1/backstage/*`` endpoints:
  - POS  → surfaces/pos-uithing-nuxt    (SURFACE-CONVERGENCE-PLAN WP1)
  - KDS  → surfaces/kds-uithing-nuxt     (station + customer pickup board)
  - Pedidos/alertas → surfaces/orders-uithing-nuxt (Gestor de Pedidos)
Their HTMX view layers were removed (OPERATOR-APPS-PLAN Fase 2). Production stays
on Django/HTMX until its dedicated app (Fase 4).
"""

from .production import (
    production_advance_step_view,
    production_kds_cards_view,
    production_kds_finish_view,
    production_kds_view,
)

__all__ = [
    "production_advance_step_view",
    "production_kds_cards_view",
    "production_kds_finish_view",
    "production_kds_view",
]
