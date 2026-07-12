# Produção — production-nuxt

Headless operator surface for the bakery floor (**Produção**, served on the
`fournil.` subdomain). Replaces the HTMX "KDS de produção" with a dedicated
Nuxt/UI-Thing app, consuming the canonical projection/action contract at
`api/v1/backstage/production/*` — no business rule is copied; the orchestrator
(Craftsman) decides.

- **Stable name:** `production-nuxt` (by function, like `pos-`/`kds-`/
  `orders-nuxt`). `fournil.` is only the public host; never hardcode it
  (it lives in the deploy spec).
- **Gate:** `backstage.operate_production` (staff operator, granted to Cozinha/
  Gerente). Log into the Django admin first to get the session cookie, then open
  the app.
- **Form factor:** tablet/touch-first, light theme (dark available via the toggle
  for the back-of-house floor).

## Telas

- **Chão ao vivo** (`/`) — started WorkOrders board: advance step, finish (with
  material-shortage override), void. The old HTMX production KDS, now Nuxt.
- **Planejamento** (`/plan`) — the production matrix: per-SKU
  planned/started/finished totals + demand suggestion, inline plan + start.

## Dev

```bash
npm ci
npm run dev          # http://127.0.0.1:3005  (navigate via 127.0.0.1, never localhost)
npm run test         # vitest — pure presentation layer
```

Set `NUXT_DJANGO_BASE_URL` to the Django/BFF origin (default `http://127.0.0.1:8000`).

## Layout

- `app/pages/index.vue` — live floor board (started WorkOrders).
- `app/pages/plan.vue` — planning matrix.
- `app/composables/useProductionKds.ts` — live-floor read-side (fetch + 30s poll) + actions.
- `app/composables/useProductionBoard.ts` — planning read-side + plan/start actions.
- `app/presentation/production.ts` — pure board shaping (tones, affordances, shortage parsing).
- `app/types/production.ts` — TS mirror of the Django production projections.
- `server/utils/djangoProxy.ts` + `server/api/v1/[...path].ts` — Django proxy (CSRF).
