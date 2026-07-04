# Gestor de Pedidos — orders-nuxt

Headless operator surface for managing live orders (the **Gestor de Pedidos**,
served on the `gestor.` subdomain). Replaces the Admin/Unfold order console with a
dedicated Nuxt/UI-Thing app, consuming the canonical projection/action contract at
`api/v1/backstage/orders/*` — no business rule is copied; the orchestrator decides.

- **Stable name:** `orders-nuxt` (by function, like `pos-`/`kds-nuxt`).
  `gestor.` is only the public host; never hardcode it (it lives in the deploy spec).
- **Gate:** `shop.manage_orders` (staff operator, granted to Caixa/Gerente). Log into
  the Django admin first to get the session cookie, then open the app.
- **Form factor:** desktop-first, responsive (board side-by-side on desktop; stacks on
  tablet/phone — the owner often tracks orders from a phone).

## Dev

```bash
npm ci
npm run dev          # http://127.0.0.1:3004  (navigate via 127.0.0.1, never localhost)
npm run test         # vitest — pure presentation layer
```

Set `NUXT_DJANGO_BASE_URL` to the Django/BFF origin (default `http://127.0.0.1:8000`).

## Layout

- `app/pages/index.vue` — order board (Entrada / Preparo / Saída), realtime.
- `app/pages/[ref].vue` — order detail (items, timeline, notes, actions).
- `app/composables/useOrdersBoard.ts` — board read-side (fetch + 30s poll + SSE) + actions.
- `app/composables/useOrderDetail.ts` — detail read-side + actions.
- `app/presentation/board.ts` — pure view transforms (unit-tested in `tests/`).
- `app/types/orders.ts` — TS mirror of the Django order projections.
- `server/` + `app/utils/api.ts` — Django proxy/BFF bridge (CSRF handled there).
