"""Backstage views package.

All operator surfaces migrated to dedicated Nuxt/UI-Thing apps served via the
canonical ``api/v1/backstage/*`` endpoints:
  - POS        → surfaces/pos-nuxt        (SURFACE-CONVERGENCE-PLAN WP1)
  - KDS        → surfaces/kds-nuxt         (station + customer pickup board)
  - Pedidos    → surfaces/orders-nuxt      (Gestor de Pedidos)
  - Produção   → surfaces/production-nuxt  (fournil. — Fase 4)
Their HTMX view layers were removed, and production EXECUTION (planejar,
iniciar, concluir, entrada direta) is exclusive to the Fournil (split canônico
WP-PE4). What remains in ``views/production.py`` are the SHARED read helpers
consumed by the Admin/Unfold production console (``render_production_surface``).
"""
