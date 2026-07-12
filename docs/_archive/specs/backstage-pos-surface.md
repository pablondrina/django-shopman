# Backstage POS Surface Spec

> **ARQUIVADA (2026-07-11).** Esta spec de UX descrevia as superfícies POS da era
> `/gestor/pos/` (Django-rendered). As fontes canônicas atuais são
> [`docs/specs/pos.md`](../../specs/pos.md) (spec de domínio/app) e
> [`docs/reference/backstage-pos-surface-contract.md`](../../reference/backstage-pos-surface-contract.md)
> (contrato de projection/action); a superfície viva é `surfaces/pos-nuxt`.

Status: canonical UX/surface spec  
Date: 2026-05-23  
Scope: operator POS surfaces backed by `docs/specs/pos.md` and `docs/reference/backstage-pos-surface-contract.md`.

## Benchmark Evidence

The surface uses Odoo POS as UX benchmark evidence only, especially its
restaurant/table-first flow, kitchen handoff affordance and dedicated payment
screen. The benchmark references are:

- Odoo 18 Point of Sale:
  `https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale.html`
- Odoo 18 Restaurant features:
  `https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/restaurant.html`
- Odoo 18 Discounts:
  `https://www.odoo.com/documentation/18.0/applications/sales/point_of_sale/pricing/discounts.html`

These references may inform navigation, screen focus and operator ergonomics.
They do not define Shopman domain rules; backend projections/actions remain the
only authority.

## Objective

The Backstage POS surface lets an operator sell under pressure with minimal
ambiguity: open the cash shift, select or create a tab, add products, identify
the customer, choose pickup/delivery and payment, review the total, commit the
order, and recover from errors without losing the sale.

The surface renders backend projections/actions and sends canonical intents. It
does not create business rules.

## Personas And Contexts

| Persona | Context | Needs |
| --- | --- | --- |
| Experienced counter operator | Peak line, keyboard/scanner/touch mixed | Fast tab/product switching, visible blockers, no duplicate CTA. |
| New operator | Training shift | Obvious next action and safe destructive actions. |
| Manager | Discount, cash divergence, correction | Clear approval prompts, audit trail, shift visibility. |
| Delivery desk | Phone/order handoff | Address, promise, cash-on-delivery (COD) state and customer memory. |
| Support/fiscal operator | Printer/fiscal/payment issue | Terminal health, order ref and recovery trail. |

## Hyper Focus

Every POS moment must answer in three seconds:

- where the operator is;
- which tab/shift/order matters;
- which primary action is next;
- what blocks that action;
- how to recover.

Do not show two primary CTAs for the same decision. Critical states must be
visible without tooltip.

## Screen Blueprint

### Operator Access

- Trigger: no Django session, not staff or missing `backstage.operate_pos`.
- Primary action: open Django Admin login without taking credentials inside the
  POS surface. In production the login may return to `/pos/`; in local dev it
  may return to `/admin/` and keep the POS tab open so the operator can refresh
  after login.
- Secondary action: refresh after login.
- No local credential form.

### Cash Shift

- Trigger: no open cash shift, or operator explicitly opens cash panel.
- Header: terminal label, operator, shift state.
- Closed state primary action: open shift with opening amount.
- Open state primary actions: register movement, close shift.
- Close shift requires explicit confirmation and notes/count input.
- Movement kinds come from `cash_management.movement_kinds`.
- Empty state: "open cash shift before selling" with open-shift form.
- If the terminal is already open under another operator, show a blocked
  terminal state with operator, terminal and shift id. Do not show "Abrir caixa"
  as the primary action because the backend will reject it.

### Tab Board

- Primary task: choose or create a tab/comanda.
- Required blocks:
  - search/scanner input;
  - all/open filter;
  - grid/list toggle;
  - in-use tabs first;
  - visible item count, total and customer preview.
- Empty state:
  - no tabs: concrete action to type/create tab;
  - no search result: clear search or create with typed ref.

### Sale Workspace

- Primary task: add products to the active sale.
- Required blocks:
  - product search/scanner input;
  - collection rail ordered by favorite collections when projected;
  - grid/list product view;
  - cart panel always visible on desktop and immediately reachable on mobile.
- Product tile/list:
  - projected name, SKU, price and D-1 flag;
  - current quantity if in cart;
  - no stock/price inference outside projection.

### Current Ticket / Cart

- Primary task: keep ticket recoverable and ready for checkout.
- Required blocks:
  - tab identity or "quick sale";
  - line items with increment, decrement and explicit remove;
  - display total from projected line prices only as interim display;
  - quick customer name/phone and lookup action;
  - save/hold action and checkout action.
- Destructive clear action requires confirmation.

### Checkout

- Primary task: review and commit the sale.
- Checkout is a dedicated workspace, not a squeezed drawer inside the product
  sale view. On desktop/tablet it uses the full available width in three clear
  zones: comanda/items, sale data that can alter the order, and
  payment/conference/final action. On mobile it stacks as a single focused flow.
- The operator must always have an explicit "back to tab/order" action that
  preserves the draft and returns to item entry.
- Required order:
  1. sale data that can affect total or required fields: fulfillment
     pickup/delivery, manual discount, manager approval, customer/fiscal
     customer fields and receipt/fiscal options;
  2. payment method/collection, split tender lines and cash amount/change;
  3. backend sale review result;
  4. final commit.
- Critical checkout fields must be visible by default. A surface may collapse
  secondary detail on small screens, but it must not hide fulfillment, discount,
  customer/fiscal, receipt or payment behind unopened accordions on desktop.
- The final commit CTA must be visually and structurally after the payment
  controls and final review. It must not appear above the payment method or as
  the first action in checkout.
- The sale screen must not show duplicate checkout CTAs in the same visual
  focus. Keyboard shortcuts may remain, but the visible primary checkout action
  belongs to the ticket/cart context where the total and blockers are visible.
- If checkout data changes after review, the primary action must return to
  review before committing. The surface must not hide an implicit review inside
  the same click that commits a sale.
- Re-reviewing from inside checkout must preserve the operator's current
  payment/customer/fulfillment draft. Reconciliation reloads are allowed when
  entering checkout from item entry, but they must not wipe tender lines or cash
  received during checkout.
- Destructive tab/cart actions must not be visually promoted inside checkout.
  Clearing or releasing a tab belongs to the ticket editing context, not the
  payment/finalization context.
- Disabled future modules, such as KDS or order queue shortcuts without
  canonical actions, must not appear in the primary POS rail. They add noise and
  imply unavailable workflows.
- Review result must show backend subtotal, discount, delivery fee, total,
  tender total, warnings and change.
- Payment amount shortcuts, cash exact/change suggestions and split tender
  auto-fill require an authoritative `review_sale` total. If review is missing
  or stale, payment controls may select a method, but amount helpers must ask
  the operator to review the total first.
- Final submit must use the same `client_request_id` as the review attempt.
- Split payment must expose editable tender lines for method, amount and
  collection. The surface may show the local difference as guidance, but backend
  review is the authority for warnings; final close must return structured
  recovery if the lines do not close the total.
- PIX/card terminal payment must show the selected provider readiness in the
  checkout payment block. After final close, if backend returns payment display
  artifacts, PIX shows QR/copia-e-cola and card shows the hosted payment link.
  These artifacts are not payment confirmation.
- Manual discount must use projected discount types/reasons. The surface sends
  type/value/reason and displays backend-reviewed discount. Manager credentials
  are requested only when backend review says approval is required.
- Reopened saved tabs must not replay backend-generated default tender lines as
  operator payment input. Explicit split tender drafts may be restored.

### Result And Correction

- Success shows order ref, final state ("order created/confirmed/pending") and
  action to open the order queue/detail.
- When `close_sale.payment` is present, success also shows the required payment
  artifact and gateway message without claiming capture.
- Recent correction/cancel uses projected `cancel_recent_sale`, requires
  confirmation and reason when useful.
- Result must never imply fiscal/payment completion unless backend says so.

### Kitchen / Production Handoff

- Sending an in-progress tab/order to kitchen/KDS before payment is a canonical
  gap, not a surface concern.
- The surface may not fake this by renaming `save_tab` or by locally marking
  items as sent. A future implementation needs a backend action such as
  `send_tab_to_production`, with idempotency, item delta, cancellation/reprint
  behavior and permission/audit contract.

### Terminal Health

- Compact button in header, expanded panel on click.
- Items: connection, fiscal status, printer, cash drawer, scanner, payment
  terminal and customer display when projected.
- Provider readiness from `provider_readiness` may add Focus NFe/Efí/Stripe
  rows. It is diagnostic only; sale/payment/fiscal outcomes still come from
  canonical actions and responses.
- Warning/error states use visible labels, not only color.

### Offline / Degraded Journal

Current POS release does not support offline commit. When the backend is not
reachable, the surface preserves the draft, blocks review/close and tells the
operator to reconnect before finalizing.

Production offline is required roadmap work. When ADR-013 is implemented, a
surface that supports offline retry must show a journal with client request id,
payload hash, total, last attempt, last error and retry action.

Block cash close while a future local critical queue is pending. Journal rows
are not orders.

## Building Blocks

| Block | Data source | Notes |
| --- | --- | --- |
| POS shell | `pos`, `shift`, `tabs` projection | No generic backoffice chrome as primary frame. |
| Cash panel | `cash_runtime`, `cash_management` actions | Backend-first shift operations. |
| Tab picker | `tabs`, `tab_lifecycle` | Scanner/keyboard/touch ready. |
| Product browser | `products`, `collections`, `favorite_collection_refs` | Search is local over projected index. |
| Ticket panel | local draft + projected line prices | Reconciles on save/review. |
| Customer memory | `customer_lookup` projection | Favorite/last-order actions only when product exists in projected catalog. |
| Address block | `address_autocomplete`, saved addresses | Structured payload preferred. |
| Payment block | `payment_methods`, `payment_collections`, `checkout.fields` | Tender validation is backend. |
| Discount/approval block | `discount_types`, `discount_reasons`, review response | Backend calculates discount and approval threshold. |
| Review summary | `review_sale` response | Authoritative total preview. |
| Health panel | terminal/fiscal/provider readiness projections | Operator-readable diagnostics. |

## Main Flows

### Open Shift

1. Surface loads `GET /api/v1/backstage/pos/`.
2. If open shift is required and missing, show Cash Shift screen.
3. Operator enters opening amount and submits `open_cash_shift`.
4. Refresh projection.
5. Move to Tab Board.

### Sale With Tab

1. Operator searches/scans tab.
2. Surface calls projected `open_tab`.
3. Surface focuses product search.
4. Operator adds products and optional customer data.
5. Autosave/save uses projected `save_tab`.
6. Checkout calls `review_sale`; payment gaps appear as warnings, not as a
   blocker to entering checkout.
7. Final submit calls `close_sale` with the same `client_request_id`.
8. Refresh projection and clear local draft after success.

### Direct Checkout

Allowed only when `tab_lifecycle.allows_direct_checkout_without_tab` is true.
The sale can start without a tab, but save/hold requires associating the draft
with a tab when `requires_tab_before_save` is true.

### Delivery / COD

1. Operator selects delivery.
2. Surface asks for address, number, neighborhood, complement/instructions,
   delivery time and optional fee.
3. On-delivery payment is offered only when projected payment collection allows
   it.
4. Commit creates Orderman order with delivery and tender metadata.
5. COD means cash on delivery. It is settled later by canonical
   order/operator action and is not counted in the POS terminal CashShift at
   commit time.

### Customer Memory

1. Operator enters phone and triggers `customer_lookup`.
2. Surface fills ref/name/email and default address when appropriate.
3. Favorite/last-order shortcuts add only SKUs present in projected products.
4. Commit persists any new customer data through backend service.

### Close Shift

1. Operator opens Cash panel.
2. Surface shows current shift state and day summary.
3. Operator enters counted amount and notes.
4. Confirmation explains that the shift will close.
5. Surface calls `close_cash_shift` and refreshes projection.

## States

### Loading

- Skeleton for product/tab grids.
- Header remains stable.
- Do not show empty state until loading finishes.

### Empty

- No tabs: prompt to scan/type a tab.
- No products: "No sellable product in POS projection" and retry/refresh.
- Empty cart: "Add products" or "choose tab" depending on capability.
- No customer: keep optional flow and explain nothing beyond the next action.

### Errors

- 401/403: operator access screen.
- `cash_shift_required`: Cash Shift screen, preserve draft.
- intent field errors: focus matching block (`search`, `delivery_address`,
  `payment`, `receipt_email`).
- split tender errors: keep checkout open, focus payment and show the backend
  recovery instruction.
- 409/conflict: show refresh/retry and preserve local draft.
- network offline: current release blocks review/close and preserves draft;
  future offline queue is allowed only when ADR-013 capability/contract exists.
- printer/fiscal warning: show terminal health and whether order was still
  created.
- provider warning/error: show the projected row and block any local
  interpretation; operator recovery is runbook/smoke/configuration, not a
  browser-side decision.

## Translation Between Frameworks

Frameworks may change component names, not the interaction contract:

- Dialog/sheet/modal: same role if focus is trapped and destructive actions are
  confirmed.
- Segmented/radio/tabs: same role if one source of truth and labels visible.
- Card/list/table: same role if tab/product anatomy and state are preserved.
- Toast/alert/banner: choose by severity; transaction result and blocking error
  must be persistent enough to act on.
- Keyboard shortcuts can be platform-specific, but scanner/product/tab/search
  priority must remain.

## Keyboard, Scanner And Touch

Required:

- F2 or equivalent: tab board/tab input.
- F3 or equivalent: sale/product search.
- F4 or equivalent: checkout/review.
- `/` focuses product search when not editing.
- Escape backs out of checkout to items.
- Search inputs accept scanner paste/enter.
- Product and tab targets are at least touch-friendly and stable.
- No positive tabindex.

Roadmap:

- roving tabindex for product/tab/payment grids;
- plus/minus/delete item operations from keyboard;
- manager/operator switch by secure backend action.

## Accessibility

- All icon buttons have accessible names.
- Destructive dialogs name the irreversible effect.
- Critical status uses text and icon/color.
- Result/error regions use persistent alert or aria-live equivalent.
- Inputs have labels, not placeholder-only semantics.
- Touch targets stay stable across loading, hover and badge changes.

## Visual/UX Guardrails

- Operation-first, dense and calm; no marketing hero.
- No cards nested inside cards for page sections.
- No generic dashboard/backoffice chrome as the dominant POS frame.
- No duplicate search for the same mode.
- No duplicate checkout CTA in the same visual focus.
- No contradictory status between header, tab and cart.
- No local total as final amount after review exists.
- No hidden destructive action.
- Mobile/tablet keeps cash, tab, search, cart and checkout reachable without
  horizontal layout breakage.

## Acceptance Criteria

- A new implementation in another framework can reproduce screen order,
  primary/secondary actions and state behavior from this spec and the contract.
- All business facts come from `GET /api/v1/backstage/pos/`, projected actions
  or canonical action responses.
- Review and commit use `pos.sale-intent.v1`.
- Missing cash shift blocks sale review/close with backend error and visible
  cash recovery.
- Manual discount and manager approval controls are present and backed by
  backend-reviewed totals/errors.
- Offline commit is disabled in the current release; production offline follows
  ADR-013.
- Clear tab and close shift require confirmation.
- Customer lookup and address memory are projection-driven.
- Build, frontend tests and backend POS contract tests pass.
- Manual smoke covers access, cash open, tab sale, checkout review and commit
  path.
