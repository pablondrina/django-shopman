# POS Canonical Spec

Status: canonical domain/app spec  
Date: 2026-05-23  
Scope: Shopman POS / PDV operational app, channel `pdv`, backstage operator flows.

## Purpose

POS is the operator-assisted selling app for counter, pickup and local delivery
sales. It lets a staff operator open a terminal shift, select or create a POS
tab, assemble a sale from projected catalog rows, identify a customer, choose
fulfillment and tender details, review the sale, and commit it as an Orderman
order.

POS is not a separate order, payment, stock, fiscal or customer domain. It is an
operational app composed by Shopman core/orchestrator over Orderman, Payman,
Stockman, Guestman, Doorman, Craftsman, ChannelConfig, Directives, services,
projections, actions and capabilities.

## Scope

- Terminal runtime profile, operator session and cash shift.
- POS tabs/comandas as recoverable Orderman sessions.
- Catalog rows sellable on the POS channel.
- Customer lookup, customer merge/persistence and consumption memory.
- Pickup and delivery fulfillment intent.
- Payment collection at terminal or on delivery.
- Cash change, split tender lines, COD settlement metadata and shift totals.
- Fiscal/receipt intent, not fiscal implementation ownership.
- Recent sale correction inside the configured operator window.
- Recovery for validation, payment, stock, network, printer and conflict states
  when the backend exposes enough metadata.

## Non-Scope

- New order lifecycle or status vocabulary.
- A POS-specific payment lifecycle outside Payman/payment metadata.
- A POS-specific stock availability model outside Stockman and catalog
  projections.
- A POS-specific customer profile outside Guestman/Doorman.
- A POS control plane, screen command bus, remote status or UI lifecycle.
- Fiscal provider configuration beyond exposing fiscal readiness and creating
  fiscal intent on committed orders.
- Offline commit in the current release. Production offline is required
  roadmap work, but must be enabled only after the canonical journal/replay
  contract in ADR-013 exists.

## Canonical Vocabulary

| Term | Meaning | Owner |
| --- | --- | --- |
| POS terminal | Physical or digital selling point with runtime metadata. | Backstage POS runtime |
| Cash shift | Open/closed cash drawer period for one operator and terminal. | `CashShift` |
| Cash movement | Manual sangria, suprimento or ajuste inside a cash shift. | `CashMovement` |
| POS tab | Operator-facing comanda reference backed by an Orderman session. | `POSTab` + Orderman `Session` |
| POS sale intent | Versioned operator payload `pos.sale-intent.v1`. | `shopman.shop.services.pos_intent` |
| Sale review | Non-committing validation and normalized total preview. | POS service/API |
| Tender line | Payment line by method, amount, collection and status. | POS service + Orderman data |
| Payment collection | `terminal` when received in the POS shift, `on_delivery` when collected later. | POS service + Orderman data |
| COD | Cash on delivery: money received at delivery, not at the POS terminal. | Orderman/Payman/cash reconciliation |
| Recent correction | Cancel/reopen path for a recent POS order with audit reason. | POS service + cancellation service |

## Entities And Aggregates

- `POSTerminal`: terminal ref, label, channel, location, active flag and hardware
  metadata. Terminal metadata may expose favorite collections, default
  fulfillment and component adapters.
- `CashShift`: one open shift per operator and one open shift per terminal.
  Closing computes expected amount and difference from opening amount, terminal
  cash sales and cash movements.
  If a terminal is open under another operator, the runtime is blocked for the
  current operator until that shift is closed or another terminal is selected.
- `CashMovement`: positive manual movement in an open shift.
- `POSTab`: persistent operator label/reference. It does not own cart contents.
- Orderman `Session`: canonical mutable cart for in-use tabs and direct checkout.
- Orderman `Order`: canonical committed sale and operational lifecycle.
- Guestman `Customer`, `CustomerAddress`, contact points and identifiers:
  canonical customer data captured or resolved by POS.
- Payman `PaymentIntent`: canonical digital payment source when POS/tender
  requires it. Current POS terminal cash/pix/card can be external timing, but
  Payman remains owner when a gateway intent exists.

## Domain Owners

| Decision | Canonical owner |
| --- | --- |
| Which products and prices are sellable in POS | Offerman/listing + POS projection |
| Whether an item can be promised or committed | Stockman/Orderman commit validation |
| Order creation and lifecycle | Orderman/session commit/cancellation services |
| Payment gateway status | Payman |
| Cash drawer state and counted cash | `CashShift`/`CashMovement` |
| Customer identity, addresses and memory | Guestman/Doorman customer services |
| Fulfillment handoff to production/KDS/order queue | Orderman + Craftsman/KDS projections |
| Fiscal document emission and cancellation | Fiscal adapter/directives |
| Operator access | Django staff permission `backstage.operate_pos` |
| Manager approval for discount | Permission `backstage.adjust_cashshift` |
| Channel variation | ChannelConfig/policy resolution before projection |

If a POS surface needs an operational answer that is not listed above, the gap
must be canonized in a projection, action, capability or service before the
surface depends on it.

## Services, Protocols And Capabilities

Canonical services:

- `shopman.backstage.projections.pos.build_pos`
- `shopman.backstage.projections.pos.build_pos_tabs`
- `shopman.backstage.projections.pos.build_pos_shift_summary`
- `shopman.backstage.projections.pos.build_pos_customer_lookup`
- `shopman.backstage.services.pos.open_cash_shift`
- `shopman.backstage.services.pos.close_cash_shift`
- `shopman.backstage.services.pos.register_cash_movement`
- `shopman.shop.services.pos.open_pos_tab`
- `shopman.shop.services.pos.save_pos_tab`
- `shopman.shop.services.pos.clear_pos_tab`
- `shopman.shop.services.pos.review_sale`
- `shopman.shop.services.pos.close_sale`
- `shopman.shop.services.pos.cancel_recent_order`
- `shopman.shop.services.pos.reopen_recent_order_for_correction`
- `shopman.shop.services.pos_intent.parse_pos_sale_intent`

Required capabilities exposed to surfaces:

- `tab_lifecycle`
- `cash_management`
- `sale_correction`
- `idempotent_replay`
- `customer_lookup`
- `address_autocomplete`
- `live_refresh`
- fiscal readiness
- provider readiness for Focus NFe homologação/runtime, Efí PIX and Stripe card
- split tender support
- cash change support
- on-delivery cash support
- manual discount and manager approval threshold

## Projections And Actions

The POS app must expose a single top-level backstage projection:

- `GET /api/v1/backstage/pos/`

It returns:

- `pos`: terminal/catalog/checkout/actions/capabilities projection.
- `shift`: current day POS summary.
- `tabs`: active/empty tab cards.

Expected actions:

- `create_tab`
- `open_tab`
- `save_tab`
- `clear_tab`
- `review_sale`
- `close_sale`
- `cancel_recent_sale`
- `open_cash_shift`
- `close_cash_shift`
- `cash_movement`
- `customer_lookup`
- `reverse_geocode`

Actions are offered by backend projection and carry method, href,
payload_schema, idempotency and confirmation metadata. A surface must not invent
equivalent endpoints or hidden actions.

## Lifecycles

POS uses existing lifecycles only:

- Cash shift: `open`, `closed`, `void`.
- Orderman session: `open`, committed/abandoned states already provided by
  Orderman.
- POS tab projection state: `empty` or `in_use`; this is a projection label over
  Orderman session state, not an independent lifecycle.
- Order status: Orderman canonical statuses only.
- Payment status: Payman statuses when a gateway intent exists; tender line
  metadata can be `received` or `pending` but cannot become order/payment
  lifecycle.

## Mutations And Intents

The canonical sale payload is `pos.sale-intent.v1`. It accepts only the keys
exported by `POS_SALE_INTENT_PAYLOAD_KEYS`, including items, customer fields,
fulfillment fields, tender fields, fiscal/receipt fields, manual discount,
manager approval, tab identity and `client_request_id`.

Critical mutations:

- Open cash shift: creates or returns the operator's current shift; blocks when
  another operator has the terminal open.
- Close cash shift: closes the operator's open shift and computes expected cash.
- Cash movement: writes one positive movement in the open shift.
- Open POS tab: normalizes tab ref and creates or loads the tab session.
- Save POS tab: replaces mutable session data using parsed POS sale intent.
- Clear POS tab: abandons the open tab session.
- Review sale: parses the same sale intent, validates non-payment blockers and
  returns authoritative totals/warnings without committing.
- Close sale: parses, validates, writes/commits Orderman session, reconciles
  payment metadata, persists customer data and marks POS metadata.
- POS terminal digital payment: when a committed terminal sale uses a single
  `pix` or `card` method, the POS service initiates the canonical Payman adapter
  after order creation and returns display-safe payment data to the action
  response. For PIX this includes QR/copia-e-cola when the adapter provides it;
  for card this includes the hosted payment URL when the adapter provides it.
- Cancel recent sale: cancels a recent POS order through the cancellation
  service and optional correction reason.

## Invariants

- POS sale review and close require a staff operator with `backstage.operate_pos`.
- POS sale review and close require an open cash shift when
  `cash_management.requires_open_shift_for_sale` is true.
- Only one open cash shift can exist per operator and per terminal.
- A terminal occupied by another operator is a canonical cash runtime state,
  not a UI guess; projections must expose the blocking shift/operator.
- A terminal sale received in cash must be counted in the active CashShift.
- Cash on delivery is not counted in the terminal shift until settled by a
  canonical operator order action.
- Tender lines must close the reviewed total before commit.
- Incomplete split tender drafts may be saved on an open tab. `review_sale`
  returns payment warnings so the operator can enter checkout; `close_sale`
  rejects incomplete/mismatched split tenders with structured recovery before
  any order is committed.
- Generated default tender lines created while saving a tab are backend
  materialization details. They must not be replayed by surfaces as operator
  input when a tab is reopened.
- `client_request_id` is required for `close_sale` and is the idempotent replay
  key for retry. It does not enable offline commit by itself.
- Payment received on delivery is allowed only for delivery and cash/mixed
  tender. Individual on-delivery tender lines must be cash.
- Manual discount is normalized by backend from type/value/reason; above the
  configured threshold it requires manager credentials and
  `backstage.adjust_cashshift`.
- Delivery close requires a delivery address; structured address is preferred.
- Fiscal with unsupported delivery-fee shape is rejected before commit until the
  fiscal path supports it.
- Staging/homologação provider readiness is backend-owned: Focus NFe must point
  to homologação, Efí PIX must use sandbox credentials and Stripe must use
  test/sandbox keys before a staging smoke can pass.
- Focus NFe NFC-e emission is canonical adapter behavior, not surface behavior:
  homologação uses the Focus homolog URL, token Basic Auth, `ref` as the
  idempotent order reference, `completa=1`, required NFC-e fields such as
  `local_destino`, `formas_pagamento` and backend-calculated totals. The
  CNPJ emitente comes from `FOCUS_NFE_CNPJ_EMITENTE` or, when unset,
  `Shop.document`. The directive is enqueued only when the committed order
  carries `fiscal.issue_document=true`.
- The surface may show local cart totals from projected line prices, but the
  authoritative total is the review/commit response.

## Permissions

- `backstage.operate_pos`: load POS projection and execute POS actions.
- `backstage.audit_cashshift`: audit shifts.
- `backstage.adjust_cashshift`: approve discounts and adjustments.
- Production/KDS and order management keep their own permissions; POS must not
  bypass them.

## Idempotency

- `close_sale` requires `client_request_id`.
- Replaying `close_sale` with the same client request after a successful commit
  returns the existing order when no open tab session is left.
- Offline retry queues must store client request id, payload hash, last attempt,
  error and recovery action; they must not create a local order status.
- Non-critical cash/open/save operations are currently `idempotency=none` unless
  the action projection changes.

## Events And Audit

Required audit/evidence:

- Cash shift open/close with operator, terminal, timestamps and amounts.
- Cash movements with type, amount, reason and created_by.
- POS tab open/save/clear logs with operator and session.
- POS close log with order, tab, session and total.
- Order data records `origin_channel=pos`, `pos_operator`,
  `pos_committed_at`, `pos.intent_version`, `pos.terminal_ref`,
  `pos.cash_shift_id` when applicable and `pos.client_request_id`.
- Customer creation/merge metadata records POS capture origin and operator.
- Recent correction records cancellation and `pos_correction_reason`.

## Integrations

- Orderman: sessions, commit, order status and cancellation.
- Payman: digital gateway intent/status when payment is not external/manual.
  POS action responses may expose display artifacts (`qr_code`, `copy_paste`,
  `checkout_url`) but Payman remains the payment state owner.
- Stockman: availability and commit-time inventory validation.
- Guestman: customer identity, contact points, addresses, identifiers and memory.
- Doorman: operator/staff session and future device/operator verification.
- Craftsman/KDS: production tickets and fulfillment handoff after commit.
- ChannelConfig: POS channel policy, fulfillment types, payment timing and
  modifier behavior.
- Directives: fiscal emission/cancellation, payment timeout and future async
  recovery.
- Focus NFe: NFC-e adapter/readiness. In staging, only homologação is acceptable.
- Efí: PIX adapter/readiness. In staging, only sandbox credentials/certificate
  are acceptable.
- Stripe: card adapter/readiness through Checkout. In staging, only test/sandbox
  keys and webhook secret are acceptable.

## Degraded Mode

- No Django session or missing permission: surface shows operator access action.
- No open cash shift: surface shows cash-open workflow and blocks review/close.
- Network offline: current surfaces preserve draft and block review/close until
  the backend is reachable. Production offline commit is documented in ADR-013
  and requires a canonical journal/replay package before enablement.
- Printer/fiscal/payment terminal warning: projection exposes terminal health;
  the surface shows state before the critical action.
- Provider readiness warning/error: projection exposes Focus NFe/Efí/Stripe
  readiness without secret values; the surface may display it but must not
  override provider, payment or fiscal state locally.
- Stock/payment/customer/fiscal conflicts: backend returns field/code/recovery;
  surface focuses the affected area and asks for a projection/action extension
  when recovery is not specific enough.

## Anti-Patterns

- Creating `pos_status`, `ui_status`, `screen_command`, `remote_status` or a new
  POS lifecycle.
- Closing a sale without backend validation because the local cart looks valid.
- Counting on-delivery cash in a terminal shift before canonical settlement.
- Reading Product/Order/Session models directly from a surface.
- Hiding permission or manager approval logic in the browser.
- Computing discount, fiscal readiness, stock availability or order status in
  the surface.
- Keeping compatibility aliases as public surface contract.

## Acceptance Criteria

- POS domain behavior is documented in this spec without UI layout language.
- `GET /api/v1/backstage/pos/` exposes all facts/actions a surface needs for the
  current POS.
- `review_sale` and `close_sale` use the same parser and error contract.
- `review_sale` does not block merely because payment lines are incomplete; it
  returns warnings. `close_sale` is the payment-completion enforcement point.
- Critical sale commit is idempotent by `client_request_id`.
- Cash shift is backend-enforced for review/close when required by capability.
- Surface tests prevent non-canonical catalog/storefront/stock endpoints.
- Backend tests cover projection/actions/capabilities and sale intent parsing.
- Build and smoke for the POS surface pass before release.
- Current POS release has no offline commit; production offline must follow
  ADR-013.
