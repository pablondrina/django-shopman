# Backstage POS Hardening Report

Date: 2026-05-23  
App: POS (`pos`)  
Surface: `surfaces/pos-uithing-nuxt`  
Kind: backstage/operational surface

## Sources Audited

- Canonical/backend docs: `docs/specs`, `docs/reference`, `docs/guides`, `docs/decisions`, `docs/plans`, `docs/reports`.
- POS backend: `shopman/backstage/projections/pos.py`, `shopman/backstage/api/operations.py`, `shopman/backstage/api/urls.py`, `shopman/backstage/services/pos.py`, `shopman/backstage/services/pos_terminal.py`, `shopman/backstage/models/cash_register.py`, `shopman/backstage/models/pos.py`.
- POS service/intent layer: `shopman/shop/services/pos.py`, `shopman/shop/services/pos_intent.py`.
- Gateway/fiscal/payment adapters: `shopman/backstage/services/gateway_smoke.py`,
  `shopman/backstage/services/integration_readiness.py`,
  `shopman/shop/adapters/fiscal_focusnfe.py`,
  `shopman/shop/adapters/payment_efi.py`,
  `shopman/shop/adapters/payment_stripe.py`.
- Mature POS reference: `shopman/backstage/views/pos.py`, `shopman/backstage/templates/pos/index.html`, `shopman/backstage/templates/pos/cash_open.html`.
- External UX benchmark evidence: Odoo 18 Point of Sale
  (`https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale.html`),
  Odoo 18 Restaurant features
  (`https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/restaurant.html`),
  and Odoo 18 Discounts
  (`https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/pricing/discounts.html`).
- Nuxt POS surfaces: `surfaces/pos-uithing-nuxt`, plus stale/maturity comparison against `surfaces/backstage-nuxt/app/pages/pos.vue`.
- Tests: POS headless contract, intent, cash register/service, tabs, shift summary, discount notes, cancellation and frontend guardrails.

## Behavior Matrix

| Behavior | Classification | Evidence / Action |
| --- | --- | --- |
| POS projection, tabs, products, checkout, actions and capabilities | Already canonical | `build_pos`, `build_pos_tabs`, `/api/v1/backstage/pos/`. |
| Sale review/close through `pos.sale-intent.v1` | Already canonical | `review_sale`, `close_sale`, intent parser and headless tests. |
| Tab open/save/clear | Already canonical | `open_pos_tab`, `save_pos_tab`, `clear_pos_tab`, projected actions. |
| Customer lookup, memory and saved address | Already canonical | `build_pos_customer_lookup`, checkout/customer capability. |
| Cash open/close/movement | Already canonical | `CashShift`, `CashMovement`, projected cash actions. |
| Backend block for review/close without open shift | Canonical gap fixed | API and Django POS close now return `cash_shift_required` before commit path. |
| POS UI Thing cash workflow | Surface detail backed by canon | Added `PosCashPanel` wired to projected cash actions and capabilities. |
| Product/search/grid/list/cart layout | Surface detail | Kept in surface spec; no domain ownership. |
| Local cart draft before save/review | Surface detail with canonical reconciliation | Preserved as draft only; review/commit remains backend authority. |
| Split payment/tender lines | Canonical gap fixed in excellence pass | Projection now exposes `mixed`; UI Thing renders editable tender lines; review warns on gaps and close returns structured payment recovery when lines do not close total. |
| Checkout review vs final close | Canonical/UX gap fixed | `review_sale` no longer blocks checkout entry for incomplete payment; `close_sale` remains the enforcement point. |
| Manual discount and manager approval | Canonical/surface gap fixed | Backend normalizes discount from type/value/reason; UI Thing renders projected discount controls and manager credentials; API close returns structured approval errors. |
| Focus NFe homologação readiness | Canonical gap fixed | Added non-secret provider readiness service and `smoke-gateways-sandbox` checks for Focus NFe homologação; staging rejects production endpoint/env. |
| Focus NFe NFC-e adapter compliance | Canonical gap fixed | Aligned NFC-e payload with the current Focus reference: homolog URL, Basic Auth token, `completa=1`, `local_destino`, canonical totals/payment forms, CNPJ fallback from `Shop.document` and no emission unless `fiscal.issue_document=true`. |
| Efí PIX sandbox readiness | Canonical gap fixed | Readiness now validates adapter, sandbox mode, credentials, certificate path, PIX key and webhook token. |
| Stripe test readiness | Canonical gap fixed | Readiness validates card adapter, test secret/public key shape, webhook secret and public domain shape. |
| POS terminal integration diagnostics | Surface detail backed by canon | POS projection exposes `provider_readiness`; UI Thing health panel renders Efí/Stripe diagnostic rows and fiscal row comes from backend readiness. |
| POS PIX payment artifact | Canonical gap fixed | `close_sale` now initiates the canonical Payman adapter for single-method terminal PIX/card and returns display-safe QR/copia-e-cola or checkout URL when available. |
| POS checkout workspace | Surface hardening | Reworked the UI Thing flow so checkout is a dedicated workspace with order summary/review beside a wide payment/customer/fulfillment/fiscal panel, rather than a squeezed payment block in the product screen. |
| POS checkout action hierarchy | Surface hardening | Final commit now appears after payment, optional data and final review; guardrail prevents `Finalizar venda` from appearing before payment/review in source hierarchy. |
| POS visible CTA discipline | Surface hardening | Removed duplicate sale-screen checkout CTA, hid destructive clear-tab action during checkout, and made stale checkout data return to review before final commit. |
| POS checkout re-review draft preservation | Surface bug fixed | Re-reviewing inside checkout no longer reloads the saved tab before review, preventing freshly-entered tenders/customer/delivery data from being wiped. |
| POS checkout total-affecting data order | Surface hardening | Fulfillment, discount, approval, customer/fiscal and receipt data now appear before payment, so operators set total-affecting data before entering tenders. |
| POS payment amount authority | Surface hardening | Cash exact/change shortcuts and split tender auto-fill now require an authoritative backend review total; stale checkout data prompts `Revisar total` before receiving. |
| POS primary navigation noise | Surface hardening | Removed disabled `Pedidos`/`KDS` placeholders from the active POS rail; unavailable modules must not compete with current operation until canonical actions/projections exist. |
| Kitchen/KDS send from open tab | Canonical gap identified | Do not fake with `save_tab`; needs a canonical `send_tab_to_production`-style action with idempotency, item delta, printer/KDS recovery, permission and audit semantics. |
| Saved tab payment draft | Canonical/surface gap fixed in excellence pass | Backend no longer exposes generated default tender lines as explicit input; explicit split drafts can survive save/reopen. |
| Field-specific recovery | Surface gap fixed in excellence pass | POS UI Thing reads backend `error.focus`, `error.field`, `error.recovery`, routes cash/payment/delivery/receipt focus and shows next action. |
| Local dev operator login route | Surface/dev ergonomics fixed | POS login opens in another tab and returns to `/admin/` in dev to avoid Django `/pos/` 404; production remains configurable. |
| Direct hardcoded paths in stale backstage Nuxt page | Legacy/descartable | Not used as reference; contract requires projected actions. |
| UI-derived order/payment/cash status | Prohibited | Added docs/guardrails against local lifecycle/status. |

## Canonical Gaps

- Fixed: review and close endpoints now enforce an open cash shift when POS cash management requires it.
- Fixed: split payment is no longer only a backend capability; it is projected,
  rendered and validated with structured recovery.
- Fixed: stale/generated tender replay from saved tabs is blocked at backend and
  surface serializer layers.
- Fixed: staging/homologação gateway readiness now includes Focus NFe, Efí PIX
  and Stripe, and fails honestly on missing credentials or live/production
  configuration in staging.
- Fixed: selecting PIX in checkout no longer results in silence after close;
  when the adapter can create a payment, the action response includes the
  payment display artifact and the UI renders it.
- Decision recorded: current release has no offline commit. Production offline remains required roadmap work and must follow ADR-013 before enablement.
- Remaining: printer/fiscal/payment terminal recovery is projected as health/readiness, but detailed retry actions are not yet canonical.
- Remaining: COD settlement after delivery needs a canonical operator action outside this POS hardening slice.

## Decisions

- The Django/HTMX POS is the mature UX reference, not the domain source of truth.
- `docs/specs/pos.md` is the canonical app/domain spec; layout lives only in the surface spec.
- POS UI Thing must use `pos.actions[]` and `pos.checkout.capabilities`, with fallback paths matching only documented canonical endpoints.
- Missing cash shift is a backend-first blocker for review/close, not only a surface warning.
- Cash panel UX is a surface concern, but movement kinds and mutation refs are backend-projected.

## Changes Made

- Added canonical POS domain spec: `docs/specs/pos.md`.
- Added backend/projection/action/capability contract: `docs/reference/backstage-pos-surface-contract.md`.
- Added framework-portable surface spec: `docs/specs/backstage-pos-surface.md`.
- Added API/Django close enforcement for missing open cash shift with stable `cash_shift_required` recovery metadata.
- Added `PosCashPanel` and wired POS UI Thing cash open/close/movement to projected actions.
- Added frontend guardrail expectations for cash management and backend tests for missing shift review rejection.
- Updated POS close fixtures to open a cash shift where tests exercise later close errors.
- Deprecated the older Backstage Nuxt POS route: Backstage navigation now points to the active POS surface URL, and `surfaces/backstage-nuxt/app/pages/pos.vue` is only a bridge.
- Excellence pass: added projected `mixed` payment option, split tender UI,
  tender-draft serialization guardrails, structured backend split-payment
  errors, and field-specific UI recovery.
- Excellence pass: made checkout review non-blocking for incomplete payment and
  kept final close as the backend payment-completion enforcement point.
- Excellence pass: added manual discount/manager approval UI in POS UI Thing and
  canonical backend discount normalization from type/value/reason.
- Excellence pass: adjusted local dev operator login flow to avoid returning to
  an unserved Django `/pos/` path while preserving production `/pos/`
  configurability.
- Staging gateway pass: added canonical provider readiness service, Focus NFe
  homologação checks to `smoke_gateways`, Efí/Stripe staging guardrails, POS
  `provider_readiness` capability and health-panel diagnostics.
- Focus NFe doc pass: verified the current NFC-e reference and hardened the
  adapter so first homologation tests use Focus homologação URL, Basic Auth,
  `POST /v2/nfce?ref=...&completa=1`, required `local_destino`, payment forms
  and backend-owned fiscal intent.
- Payment display pass: POS close now initiates canonical Payman payment for
  single-method terminal PIX/card and POS UI Thing renders PIX QR/copia-e-cola
  or card checkout URL from the action response.
- Odoo benchmark pass: used the official restaurant POS workflow as UX evidence
  for floor/table-first navigation, kitchen handoff affordance and a dedicated
  payment screen, while keeping Shopman backend projections/actions as the only
  authority.
- Backstage bridge polish: replaced the missing `lucide:bread` workspace icon
  with an installed Lucide icon so `/pos` bridge reloads without that console
  warning.
- Design hierarchy pass: checkout now follows data -> payment -> final review
  -> final commit, with `Finalizar venda` only at the end of the flow.
- Design audit follow-up: removed duplicate checkout entry from the sale search
  bar, kept the visible checkout CTA in the ticket context, hid clear-tab action
  while in checkout, and changed the primary checkout action to `Revisar venda`
  whenever the backend review is stale/missing.
- Navigation audit follow-up: removed disabled `Pedidos`/`KDS` placeholders from
  the active POS rail. They return only when backed by canonical projection and
  action contracts.
- Checkout re-review bugfix: entering checkout may still reconcile the tab from
  backend, but re-reviewing while already in checkout preserves the current
  operator payment/customer/fulfillment draft.
- Checkout order pass: moved total-affecting data before payment, matching the
  operational sequence observed in Odoo: complete/adjust the order, then enter
  payment, then validate.
- Payment authority pass: cash presets and split tender auto-fill no longer use
  local cart totals when checkout data invalidates review; the operator must
  run backend review before amount helpers are enabled.
- 2026-05-25 rigorous follow-up: replaced the remaining cart-like checkout
  layout with a full-width three-zone checkout station: comanda/items, sale
  data, and payment/conference/final action. Critical fields are open by
  default on desktop; checkout is no longer semantically rendered as an aside.
- 2026-05-25 cash runtime fix: authenticated smoke found a contradictory state
  where projection said "open cash" but the action rejected because the terminal
  was already open by another operator. `cash_runtime.status=terminal_occupied`
  now projects the blocking operator/shift and the surface shows a blocked
  terminal state instead of an impossible `Abrir caixa` action.

## Tests And Build

- `npm run test` in `surfaces/pos-uithing-nuxt`: 12 passed.
- `npm run build` in `surfaces/pos-uithing-nuxt`: passed; only existing sourcemap/pure annotation warnings from Nuxt/Tailwind/VueUse build chain.
- `git diff --check`: passed.
- `.venv/bin/python -m pytest shopman/backstage/tests/test_pos_headless_surface_contract.py shopman/backstage/tests/test_pos_intent_contract.py shopman/backstage/tests/test_pos_cash_service.py shopman/backstage/tests/test_pos_cash_register.py shopman/backstage/tests/test_pos_cancel.py shopman/backstage/tests/test_pos_discount_notes.py shopman/backstage/tests/test_pos_tabs.py shopman/backstage/tests/test_pos_shift_summary.py -q`: 84 passed.
- Browser smoke: `http://127.0.0.1:3002/` loaded with Django at `127.0.0.1:8000`; unauthenticated operator state rendered without PDV-unavailable state. Screenshot: `/tmp/shopman-pos-smoke-2026-05-23.png`.
- Browser smoke: `http://localhost:3001/pos` bridge reloads and points to the
  active POS surface without the previous missing-icon warning.
- Excellence pass targeted checks:
  - `.venv/bin/python -m pytest shopman/backstage/tests/test_pos_headless_surface_contract.py shopman/backstage/tests/test_pos_discount_notes.py -q`: 20 passed.
  - `npm run test` in `surfaces/pos-uithing-nuxt`: 12 passed.
  - `npm run build` in `surfaces/pos-uithing-nuxt`: passed with only existing Nuxt/Tailwind/VueUse warnings.
- Gateway staging readiness checks:
  - `.venv/bin/python -m pytest shopman/backstage/tests/test_integration_readiness.py shopman/backstage/tests/test_gateway_smoke.py shopman/backstage/tests/test_pos_headless_surface_contract.py -q`: 23 passed.
  - `.venv/bin/python -m pytest shopman/backstage/tests/test_integration_readiness.py shopman/backstage/tests/test_gateway_smoke.py shopman/backstage/tests/test_pos_headless_surface_contract.py shopman/shop/tests/test_fiscal_focusnfe.py shopman/shop/tests/test_stripe_checkout_session.py shopman/shop/tests/test_payment_webhooks.py -q`: 59 passed.
  - `.venv/bin/python -m pytest shopman/backstage/tests/test_pos_tabs.py shopman/backstage/tests/test_pos_headless_surface_contract.py shopman/backstage/tests/test_pos_discount_notes.py shopman/backstage/tests/test_pos_cancel.py shopman/backstage/tests/test_pos_cash_service.py shopman/backstage/tests/test_pos_cash_register.py shopman/backstage/tests/test_pos_shift_summary.py shopman/backstage/tests/test_pos_intent_contract.py shopman/backstage/tests/test_integration_readiness.py shopman/backstage/tests/test_gateway_smoke.py -q`: 95 passed.
  - `.venv/bin/python -m pytest shopman/backstage/tests/test_pos_headless_surface_contract.py shopman/backstage/tests/test_pos_tabs.py shopman/backstage/tests/test_pos_discount_notes.py shopman/backstage/tests/test_pos_cancel.py shopman/backstage/tests/test_pos_cash_service.py shopman/backstage/tests/test_pos_cash_register.py shopman/backstage/tests/test_pos_shift_summary.py shopman/backstage/tests/test_pos_intent_contract.py shopman/backstage/tests/test_integration_readiness.py shopman/backstage/tests/test_gateway_smoke.py shopman/shop/tests/test_payment_webhooks.py shopman/shop/tests/test_stripe_checkout_session.py -q`: 129 passed.
  - `.venv/bin/python -m pytest shopman/shop/tests/test_fiscal_focusnfe.py shopman/shop/tests/test_services.py::TestFiscalService shopman/backstage/tests/test_integration_readiness.py shopman/backstage/tests/test_gateway_smoke.py -q`: 22 passed.
  - `.venv/bin/python -m pytest shopman/backstage/tests/test_pos_headless_surface_contract.py shopman/backstage/tests/test_pos_tabs.py shopman/backstage/tests/test_pos_intent_contract.py shopman/backstage/tests/test_pos_discount_notes.py shopman/backstage/tests/test_pos_cancel.py shopman/shop/tests/test_lifecycle.py::TestOnCompleted -q`: 58 passed.
  - `.venv/bin/python manage.py smoke_gateways --sandbox-only --json`: `passed_local_sandbox_blocked`; Efí sandbox and Stripe test are ready in this local environment, Focus NFe/iFood/ManyChat remain honestly blocked until credentials are installed.
- 2026-05-25 follow-up checks:
  - `.venv/bin/python -m pytest shopman/backstage/tests/test_pos_headless_surface_contract.py shopman/backstage/tests/test_pos_cash_service.py -q`: 22 passed.
  - `npm run test -- --run` in `surfaces/pos-uithing-nuxt`: 12 passed.
  - `npm run build` in `surfaces/pos-uithing-nuxt`: passed; only existing Nuxt/Tailwind/VueUse sourcemap/pure annotation warnings.
  - `git diff --check`: passed.
  - Authenticated Browser DOM smoke: cash terminal occupied state rendered
    correctly, stale local admin shift was closed for smoke, `codex_pos_visual`
    opened cash, comanda `#1010` entered checkout, PIX selection invalidated
    stale review, `Revisar total` restored backend review, and `Finalizar venda`
    appeared only after payment plus final review. Browser screenshot capture
    timed out in the current in-app browser session, so evidence is DOM/console;
    console errors were empty.

## Real Pending Items

- Add a first-class canonical offline retry/journal projection before enabling offline POS commits, following ADR-013.
- Add real external sandbox smoke calls after staging secrets are installed for
  Focus NFe, Efí and Stripe; current code validates readiness and keeps local
  fixture contracts, but does not call provider sandboxes without credentials.
- Add canonical recovery actions for printer/fiscal/payment-terminal failures where recovery is more than health display.
- Add canonical COD settlement/reconciliation action for delivery cash.
- Add canonical kitchen/KDS handoff for open POS tabs before payment. Required
  contract: action ref, item delta semantics, idempotency key, permission,
  audit event, printer/KDS failure recovery and cancellation/reprint behavior.
- Add order result actions for fiscal/receipt recovery and reprint once backend
  exposes canonical action refs.
- Expand visual smoke with screenshot capture once the in-app browser screenshot
  path is stable; authenticated DOM smoke now covers cash runtime, command board,
  checkout entry, PIX selection and backend re-review.
- Older `surfaces/backstage-nuxt/app/pages/pos.vue` is now deprecated as an active POS route; remaining cleanup is optional removal of unused legacy POS helpers/components from `surfaces/backstage-nuxt` once no code imports them.

## Recommendation For Next Surface

Start from the canonical app spec, then write the backend/action contract before touching UI. Treat mature surfaces as UX evidence only, and fix small backend gaps before moving behavior into another frontend.

For POS specifically, keep `surfaces/pos-uithing-nuxt` as the active Nuxt surface. Do not refit the older backstage Nuxt POS route unless a product reason justifies maintaining two POS surfaces under the same contract.
