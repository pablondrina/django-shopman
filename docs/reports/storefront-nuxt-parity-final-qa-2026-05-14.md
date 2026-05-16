# Storefront Nuxt Parity Final QA

Executed on 2026-05-15 in `America/Sao_Paulo` for WP-10 of `docs/plans/STOREFRONT-NUXT-PARITY-ACTION-PLAN-2026-05-14.md`.

## Scope

Canonical Nuxt storefront routes were audited without route aliases or duplicate compatibility routes:

- `/`
- `/menu`
- `/produto/BAGUETE`
- `/cart`
- `/checkout`
- `/login?next=/checkout`
- `/conta`
- `/sair`
- `/pedido/WP04-PAY-QMSRGSIG/pagamento`
- `/pedido/WP05-DONE-001/confirmacao`
- `/tracking/WP05-ACTIVE-001`
- `/offline`

Viewports:

- Mobile: `390x844`, touch enabled.
- Desktop: `1440x1000`.

Environment:

- Nuxt dev server: `http://127.0.0.1:3000`.
- Django backend: `http://127.0.0.1:8000`.
- Browser evidence: local Chrome through Playwright, output in `/tmp/shopman-wp10-release-gate/`.
- Codex in-app browser automation was retried during WP-10, but the current in-app pane was not exposed to automation. The release gate therefore used the mandatory local browser fallback against the same local target.

## Automated Verification

Focused backend/parity suite:

```text
247 passed, 2 skipped in 3.88s
```

Contract-only rerun after the WP-10 accessibility fix:

```text
28 passed in 0.27s
```

Nuxt production build:

```text
npm run build
Build complete
```

Build warnings were limited to known non-blocking sourcemap warnings from Nuxt/Tailwind transforms and Rollup comments in `@vueuse/core`.

## Browser Gate

Full route pass:

- File: `/tmp/shopman-wp10-release-gate/wp10-results.json`.
- Coverage: 12 routes x 2 viewports.
- Result: no hydration mismatch warnings, no route warnings, no icon warnings, no page errors, and no horizontal overflow.
- Initial findings:
  - `/cart` had one unnamed clickable upsell image link in mobile and desktop.
  - Several late desktop routes hit local QA rate limits (`429`) after the first full 24-page sweep.

Fix and rerun:

- Fixed `/cart` upsell image link with an accessible name.
- Added a parity-contract assertion for the cart upsell image link.
- Rerun file: `/tmp/shopman-wp10-release-gate/wp10-rerun-results.json`.
- Rerun screenshots:
  - `/tmp/shopman-wp10-release-gate/mobile-cart-rerun.png`
  - `/tmp/shopman-wp10-release-gate/desktop-cart-rerun.png`
  - `/tmp/shopman-wp10-release-gate/desktop-checkout-rerun.png`
  - `/tmp/shopman-wp10-release-gate/desktop-conta-rerun.png`
  - `/tmp/shopman-wp10-release-gate/desktop-sair-rerun.png`
  - `/tmp/shopman-wp10-release-gate/desktop-pedido-wp04-pay-qmsrgsig-pagamento-rerun.png`
  - `/tmp/shopman-wp10-release-gate/desktop-pedido-wp05-done-001-confirmacao-rerun.png`
  - `/tmp/shopman-wp10-release-gate/desktop-tracking-wp05-active-001-rerun.png`

Rerun result:

- `/cart`, `/checkout`, `/sair`, payment, confirmation, and tracking were clean: no browser console errors/warnings matching hydration, route, icon, or failed-resource patterns; no 4xx/5xx responses; no unnamed controls; no horizontal overflow.
- `/conta` had a detector false positive on four `UInput` fields. A label-aware rerun verified that each input has an associated native label:
  - `first_name`: `Primeiro nome`
  - `last_name`: `Sobrenome`
  - `email`: `E-mail`
  - `birthday`: `Aniversário`
- Label-aware account rerun: `/tmp/shopman-wp10-release-gate/wp10-account-label-aware-rerun.json`.

## Accessibility Checklist

- Focusable controls on audited pages have visible names after the cart fix.
- Form inputs in `/conta` are associated with native labels through `label for`.
- Destructive/sensitive actions remain protected by confirmation UI:
  - account switch/logout,
  - address deletion,
  - account deletion,
  - reservation release,
  - order cancellation,
  - reorder replacement.
- Modal contracts are covered by `shopman/storefront/tests/test_storefront_nuxt_parity_contract.py`.
- Menu live availability/search state keeps `aria-live="polite"` in the parity contract.
- Basic keyboard/focus risk was checked through semantic controls and modal/static contract coverage. No open P0/P1 a11y blocker remains.

## Performance And SEO Checklist

- Route titles are present on audited routes.
- JSON-LD is present on home, menu, and product routes in both mobile and desktop browser passes.
- Manifest, service worker, offline route, robots, sitemap, and PWA icons are covered by the WP-09/WP-10 parity test contract.
- No obvious LCP blocker or blank primary content was observed in screenshots.
- No horizontal viewport overflow was observed in mobile or desktop checks.
- Full Lighthouse was not run in WP-10; this gate used build output, browser navigation timing stability, DOM checks, and visual screenshots.

## Findings

Fixed in WP-10:

- `A11Y-ACTION-001`: the `/cart` upsell image link now has an accessible label.

Open P0/P1:

- None.

Residual P2/P3:

- P3: no full Lighthouse or axe-core audit was run in this WP. The release gate used focused browser heuristics and static parity tests.
- P3: the first full desktop sweep hit local QA rate limits after many rapid route loads. Paced reruns of the affected routes completed cleanly, so this is treated as a QA artifact rather than a product defect.

## Release Gate Decision

WP-10 acceptance is met:

- Focused tests pass.
- Nuxt build passes.
- Browser route gate was executed for the main routes in mobile and desktop, with clean reruns after the one cart a11y fix and local rate-limit pacing.
- The final QA report is saved in `docs/reports/`.
- No P0/P1 blocker remains open.
