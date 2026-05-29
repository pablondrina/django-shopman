# Backstage POS Surface Contract

Status: canonical backend/projection/action contract  
Date: 2026-05-23  
Surface class: backstage operational POS surfaces (`/gestor/pos/`, `surfaces/pos-uithing-nuxt`, future POS clients)

## Contract Rule

Backstage POS surfaces render projections and execute projected actions. They do
not own business decisions, order lifecycle, payment state, cash shift rules,
stock availability, customer identity, fiscal state or production handoff.

```text
Operator context -> POSProjection -> Action -> pos.sale-intent.v1 -> canonical service -> refreshed projection
```

The mature Django/HTMX POS runtime is a UX and flow reference. It is not the
domain canon. Any useful behavior discovered there must be backed by a
projection, action, capability, service or documented gap before another
surface depends on it.

## Canonical Endpoints

| Purpose | Method | Endpoint | Owner |
| --- | --- | --- | --- |
| POS projection | GET | `/api/v1/backstage/pos/` | `build_pos`, `build_pos_shift_summary`, `build_pos_tabs` |
| Create tab | POST | `/api/v1/backstage/pos/tabs/` | `register_pos_tab` |
| Open tab | POST | `/api/v1/backstage/pos/tabs/{tab_ref}/open/` | `open_pos_tab` |
| Save tab | POST | `/api/v1/backstage/pos/tabs/save/` | `save_pos_tab` |
| Clear tab | DELETE | `/api/v1/backstage/pos/tabs/{session_key}/clear/` | `clear_pos_tab` |
| Review sale | POST | `/api/v1/backstage/pos/sale/review/` | `review_sale` |
| Close sale | POST | `/api/v1/backstage/pos/sale/close/` | `close_sale` |
| Cancel recent sale | POST | `/api/v1/backstage/pos/sale/recent/cancel/` | `cancel_recent_order` / `reopen_recent_order_for_correction` |
| Open cash shift | POST | `/api/v1/backstage/pos/cash/open/` | `open_cash_shift` |
| Close cash shift | POST | `/api/v1/backstage/pos/cash/close/` | `close_cash_shift` |
| Cash movement | POST | `/api/v1/backstage/pos/cash/movement/` | `register_cash_movement` |
| Customer lookup | GET | `/api/v1/backstage/pos/customer/lookup/?phone={phone}` | `build_pos_customer_lookup` |
| Reverse geocode | POST | `/api/v1/geocode/reverse` | storefront geocode API |

Surfaces must use action hrefs from `pos.actions[]` when present. Fallback paths
exist only to keep code resilient while projection loading fails in tests; they
must match the canonical table above.

## Projection Shape

`GET /api/v1/backstage/pos/` returns:

```json
{
  "pos": {},
  "shift": {},
  "tabs": []
}
```

`pos` contains:

- `products[]`: `sku`, `name`, `price_q`, `price_display`, `collection_ref`,
  `is_d1`.
- `collections[]`: `ref`, `name`.
- `payment_methods[]`: canonical refs and labels for `cash`, `pix`, `card`,
  `mixed`.
- `fulfillment_options[]`: `pickup`/`delivery` options and address requirement.
- `payment_collections[]`: terminal/on-delivery options and compatible methods.
- `checkout`: sale intent contract, sections, fields, option lists and
  capabilities.
- `actions[]`: projected action contract.
- `has_open_cash_session` and `cash_runtime`.
- `terminal_ref`, `terminal_label`, `terminal_default_fulfillment_type`,
  `terminal_health_status`, `terminal_components`.
- `favorite_collection_refs`, delivery minimum and fiscal readiness.

`shift` contains current-day counts and display totals. It is read-only summary,
not a cash closing calculation.

`cash_runtime.status` is one of:

- `open`: current operator has an open shift on the projected terminal.
- `closed`: projected terminal has no blocking open shift and the current
  operator must open cash before sale review/close.
- `terminal_occupied`: the projected terminal has an open shift owned by a
  different operator. The surface must show the blocking operator/shift from
  `blocking_operator_username`, `blocking_shift_id` and `blocking_message`, and
  must not offer a local open-cash action that is known to fail.

`tabs[]` contains operator cards:

- `ref`, `display_ref`, `session_key`.
- `state`: `empty` or `in_use`.
- `status_label`, `status_class`.
- customer preview, item counts, display total, last touched time and item
  preview.

## Action Contract

Each action uses the minimal headless action fields from
`docs/reference/headless-surface-contract.md`:

- `ref`
- `kind`
- `label`
- `priority`
- `enabled`
- `reason`
- `href`
- `method`
- `payload_schema`
- `idempotency`
- `confirmation`

Expected action refs:

| Ref | Kind | Idempotency | Confirmation | Canonical decision owner |
| --- | --- | --- | --- | --- |
| `create_tab` | mutation | none | no | POS tab service |
| `open_tab` | mutation | none | no | POS tab service |
| `save_tab` | mutation | none | no | Orderman session service |
| `clear_tab` | mutation | none | destructive | Orderman session service |
| `review_sale` | mutation | none | no | POS intent/service |
| `close_sale` | mutation | required | submit confirmation by UX | POS service + Orderman |
| `cancel_recent_sale` | mutation | none | destructive | cancellation service |
| `open_cash_shift` | mutation | none | no | CashShift service |
| `close_cash_shift` | mutation | none | destructive | CashShift service |
| `cash_movement` | mutation | none | no | CashMovement service |
| `customer_lookup` | query | none | no | Guestman/customer projection |
| `reverse_geocode` | mutation | none | no | Geocode service |

## Sale Intent Payload

`review_sale` and `close_sale` accept `pos.sale-intent.v1`.

Required for commit:

- `intent_version`
- `items[]`
- `payment_method`
- `client_request_id`

Required when using a tab:

- `tab_ref` or `tab_session_key`.

Required for delivery:

- `fulfillment_type=delivery`
- `delivery_address`
- preferably `delivery_address_structured`.

Optional canonical keys:

- customer: `customer_name`, `customer_ref`, `customer_phone`,
  `customer_tax_id`, `customer_email`, `customer_memory_action`.
- fulfillment: `delivery_date`, `delivery_time_slot`, `delivery_fee_q`,
  `order_notes`.
- payment: `payment_collection`, `payment_tenders`, `tendered_amount_q`.
- fiscal/receipt: `issue_fiscal_document`, `receipt_mode`, `receipt_email`.
- approval: `manual_discount`, `manager_approval`. `manual_discount`
  carries type/value/reason; backend normalizes `discount_q`.
- runtime: `cash_shift_id`, `pos_terminal_ref` injected by backend API.

Unknown fields are rejected with `unexpected_intent_field`. Unknown versions are
rejected with `unknown_intent_version`.

`review_sale` response is the non-committing authority for subtotal, discount,
delivery fee, total, tender totals, cash change and warnings. It must let the
operator enter checkout when payment is still incomplete; `close_sale` is the
payment-completion enforcement action.

`close_sale` response may include a `payment` object for terminal digital
payments:

- `method`: `pix` or `card`;
- `status`: `pending`, `error` or `unavailable`;
- `intent_ref`: Payman intent when created;
- `amount_q` / `amount_display`;
- PIX display artifacts: `qr_code`, `copy_paste`, `expires_at`;
- card display artifact: `checkout_url`;
- `message` and optional `error`.

The surface may render these artifacts but must not treat them as payment
capture. Gateway/webhook/Payman status remains authoritative.

## Capabilities

`pos.checkout.capabilities` is the public capability object. Expected keys:

| Capability | Contract |
| --- | --- |
| `prepare_checkout_action_ref` | action ref used before checkout, currently `save_tab`. |
| `review_action_ref` | sale review action, currently `review_sale`. |
| `submit_action_ref` | commit action, currently `close_sale`. |
| `supports_split_payment` | whether tender list UI is allowed. |
| `supports_cash_change` | whether tendered cash/change UI is allowed. |
| `supports_on_delivery_cash` | whether COD may be offered for delivery. |
| `supports_customer_lookup` | customer lookup by phone is available. |
| `supports_customer_memory` | memory actions may be shown. |
| `supports_delivery_address_autocomplete` | address autocomplete may be enabled. |
| `provider_readiness` | non-secret readiness rows for Focus NFe, Efí PIX and Stripe card. |
| `fiscal_document` | fiscal runtime status: `ready`, `warning`, `error`. |
| `delivery_minimum_q` | display/validation hint; backend remains authority. |
| `requires_manager_approval_above_q` | threshold for approval credentials. |
| `address_autocomplete` | provider/key/fields/bias/reverse action metadata. |
| `tab_lifecycle` | tab ref format, allowed target states and tab actions. |
| `cash_management` | cash actions, movement kinds and shift requirement. |
| `sale_correction` | recent cancellation window and reason support. |
| `idempotent_replay` | client request id rules for online retry; it does not enable offline commit by itself. |
| `customer_lookup` | lookup key and projection guarantees. |
| `live_refresh` | refresh/push support. |

There is currently no canonical action for sending an open POS tab to
kitchen/KDS before checkout. Surfaces must not emulate this with `save_tab`,
local item flags or local "sent" status. Canonization should add a dedicated
projection/action with item delta, idempotency, printer/KDS recovery,
permission and audit semantics.

Current POS surfaces must treat offline commit as disabled. Production offline
requires the canonical journal/replay package described in ADR-013 before any
surface may enqueue sale commits while disconnected.

Surfaces may use capability flags to choose controls, but they must not derive
permissions or backend preconditions from local policy.

## Backend-First Validations

Backend must validate:

- staff/auth permission `backstage.operate_pos`;
- open cash shift for review/close when `cash_management.requires_open_shift_for_sale`;
- JSON object payload and intent version;
- allowed top-level keys only;
- non-empty item list for commit;
- positive quantities and non-negative amounts;
- delivery address for delivery;
- on-delivery payment only for delivery cash/mixed;
- individual on-delivery tender lines only for cash;
- split tender total equals sale total at `close_sale`; `review_sale` returns
  payment warnings instead of blocking checkout entry;
- cash tendered amount cannot be lower than sale total when provided at
  `close_sale`; `review_sale` returns a warning;
- receipt email required when `receipt_mode=email`;
- manager approval above discount threshold;
- fiscal constraints currently unsupported by the POS fiscal pipeline;
- staging provider readiness: Focus NFe must be homologação, Efí must be
  sandbox and Stripe must use test/sandbox keys before sandbox smoke can pass;
- Focus NFe NFC-e emission is a canonical fiscal directive after commit and
  requires `fiscal.issue_document=true`; the surface never builds Focus payloads,
  chooses Focus URLs or infers fiscal authorization;
- active tab/session existence when a tab identity is supplied;
- idempotent replay by `client_request_id`;
- recent cancellation age and order statuses.

Surface prechecks are allowed only as operator guidance. They do not replace the
backend validation.

## Permissions

| Operation | Permission |
| --- | --- |
| Load POS projection | `backstage.operate_pos` |
| Open/close shift and movement | `backstage.operate_pos` |
| Tab lifecycle and sale review/close | `backstage.operate_pos` |
| Recent sale correction | `backstage.operate_pos` |
| Manager approval | approving user must have `backstage.adjust_cashshift` |
| Cash shift audit/admin | `backstage.audit_cashshift` / admin permissions |

## Idempotency

- `close_sale` declares `idempotency=required`.
- Request key is `client_request_id`.
- A retry with the same key after commit must not create another order.
- A surface retry may resend only when the same payload and key are preserved.
- Current POS has no offline commit queue. A future queued/offline row is never
  an order and never changes cash shift totals until backend confirms commit.
- Saved tabs may preserve incomplete split tender drafts. `review_sale` returns
  warnings for incomplete/mismatched payment; `close_sale` requires split tender
  lines to close the backend-reviewed total before commit.

## Events And Audit

Minimum audit artifacts:

- cash shift open/close timestamps, operator, terminal and amounts;
- cash movement type, amount, reason and creator;
- tab open/save/clear logs with session and operator;
- order data POS metadata (`pos_operator`, `pos_committed_at`,
  `pos.intent_version`, `pos.terminal_ref`, `pos.cash_shift_id`,
  `pos.client_request_id`);
- customer POS capture metadata;
- cancellation event plus correction reason when supplied.

Future event streams may expose POS refresh, but current contract is polling via
projection refresh. A surface must not invent push state as authoritative.

## Errors And Recovery

Error payload for API intent rejection:

```json
{
  "detail": "human message",
  "error": {
    "code": "stable_code",
    "message": "human message",
    "field": "field.path",
    "focus": "surface_focus_area",
    "recovery": "operator next step"
  }
}
```

Expected important codes:

- `cash_shift_required`
- `unknown_intent_version`
- `unexpected_intent_field`
- `delivery_address_required`
- `invalid_on_delivery_payment`
- `invalid_on_delivery_tender_payment`
- `payment_tenders_required`
- `payment_tenders_total_mismatch`
- `cash_tendered_amount_too_low`
- `manager_approval_required`
- `manager_approval_invalid`
- `receipt_email_required`
- `fiscal_delivery_fee_pending`
- `cart_empty`

Recovery must be field/action specific where possible. Generic "try again" is
acceptable only for unexpected infrastructure errors.

## State Ownership

| State/fact | Owner | Surface may keep local copy? |
| --- | --- | --- |
| Product price | POS projection/Offerman | display only |
| Cart draft | Orderman session or direct local draft before commit | yes, reconciled on save/review |
| Tab state | `build_pos_tabs` | no authoritative local state |
| Cash shift open/closed | `CashShift` projection/API | no |
| Payment/tender status | POS service/Payman/Order data | no |
| Order status | Orderman | no |
| Customer profile | Guestman | draft fields only |
| Fiscal readiness | projection/fiscal settings | no |
| Provider readiness | backstage integration readiness service | no |
| Terminal health | `runtime_profile` projection | no |
| Offline retry | future ADR-013 journal keyed by idempotency | future only, not authoritative |

## Explicit Prohibitions

- No direct model/queryset access from a surface.
- No `/api/v1/catalog`, `/api/v1/storefront` or Stockman endpoints from the POS
  surface when POS projection already exposes what is needed.
- No local status for order, payment, cash shift, terminal, production or tab.
- No local inference that Focus NFe, Efí or Stripe are ready; surfaces render
  `provider_readiness`/fiscal projection and canonical action responses only.
- No replay of backend-generated default tender lines from a saved tab as if
  they were explicit operator payment input.
- No surface-created action refs or fallback business decisions.
- No total override field or admin override total.
- No offline commit in the current POS release.
- No cash close while a future local offline queue has pending critical rows;
  if the backend cannot detect a browser-local queue, the surface must block
  locally and expose the risk.
- No compatibility alias as public contract. Legacy wrappers may remain internal
  only while tests are migrated.

## Contract Tests

Required automated checks:

- Backend projection equals `projection_data(build_pos(...))`.
- Projection exposes all expected actions and capabilities.
- API review and close use the same intent parser. Payment completion is a
  review warning and a close error.
- API review/close reject missing open cash shift when required.
- Projection exposes terminal-occupied cash state when another operator owns the
  terminal shift, and cash-open returns `cash_terminal_occupied`.
- Close sale is idempotent by `client_request_id`.
- Close sale returns gateway display data for single-method PIX/card terminal
  payments when the configured adapter can create it.
- Customer lookup returns default/saved addresses and memory.
- Recent cancellation goes through canonical cancellation service.
- Frontend serializes only `pos.sale-intent.v1` keys.
- Frontend guardrail blocks non-canonical catalog/storefront/stock endpoints.
- Frontend guardrail confirms cash management uses projected actions.
- Frontend guardrail must not introduce offline commit without ADR-013
  capability/contract.
- Surface build succeeds.
