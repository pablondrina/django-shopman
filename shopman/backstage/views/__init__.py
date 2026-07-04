"""Backstage views package.

All operator surfaces migrated to dedicated Nuxt/UI-Thing apps served via the
canonical ``api/v1/backstage/*`` endpoints:
  - POS        → surfaces/pos-nuxt        (SURFACE-CONVERGENCE-PLAN WP1)
  - KDS        → surfaces/kds-nuxt         (station + customer pickup board)
  - Pedidos    → surfaces/orders-nuxt      (Gestor de Pedidos)
  - Produção   → surfaces/production-nuxt  (fournil. — Fase 4)
Their HTMX view layers were removed. What remains in ``views/production.py`` are
the SHARED helpers consumed by the Admin/Unfold production console
(``handle_production_post``, ``render_production_surface``, ``production_redirect``).
"""
