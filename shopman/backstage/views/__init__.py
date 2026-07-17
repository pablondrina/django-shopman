"""Backstage views package.

All operator surfaces migrated to dedicated Nuxt/UI-Thing apps served via the
canonical ``api/v1/backstage/*`` endpoints:
  - POS        → surfaces/pos-nuxt        (SURFACE-CONVERGENCE-PLAN WP1)
  - KDS        → surfaces/kds-nuxt         (station + customer pickup board)
  - Pedidos    → surfaces/orders-nuxt      (Gestor de Pedidos)
  - Produção   → surfaces/production-nuxt  (fournil. — Fase 4; o console
    Admin/Unfold de produção saiu no WP-ADM-7d após a paridade do WP-ADM-7b)
Their HTMX view layers were removed. What remains here is the Admin 2FA
interstitial (``two_factor.py``).
"""
