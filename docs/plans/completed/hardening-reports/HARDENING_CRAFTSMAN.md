# HARDENING_CRAFTSMAN.md

## Craftsman — hardening plan

Status: draft v1
Scope: `django-shopman/packages/craftsman`

---

## 1. Executive summary

Craftsman already has the shape of a strong headless micro-MRP kernel.

Its main strengths are:

- very small and intelligible core
- good separation between planning, execution, and queries
- strong use of string refs for agnosticity
- sensible production abstractions (`Recipe`, `WorkOrder`, `WorkOrderItem`, `WorkOrderEvent`)
- real concern for concurrency and idempotency
- viable standalone operation without mandatory external integrations

Its main hardening needs are not in the conceptual model, but in the boundaries:

- integrated mode is too tolerant of external failures
- some critical validations degrade silently
- public HTTP API is narrower than the kernel capabilities
- naming and packaging consistency still need cleanup
- identity semantics should be aligned with the suite-wide `ref` convention

Bottom line:

- as a standalone production-planning/production-ledger app: **good**
- as a suite-grade authoritative production orchestrator: **needs hardening**

---

## 2. What should be preserved

These are not problems. They are part of the package's strongest design choices and should be preserved.

### 2.1. Minimal core

The package is intentionally small: a few models, a few verbs, a compact lifecycle. That is an advantage, not a limitation.

Keep:

- `Recipe` / `RecipeItem`
- `WorkOrder`
- `WorkOrderItem` as unified material ledger
- `WorkOrderEvent` as immutable semantic audit trail
- `CraftService` as a thin facade over focused service modules

### 2.2. String refs instead of FK ownership

This is aligned with the suite architecture.

Keep:

- `Recipe.output_ref`
- `RecipeItem.input_ref`
- `WorkOrder.output_ref`
- `source_ref`
- `position_ref`
- `assigned_ref`

This is a strength. Craftsman should not own catalog, users, or inventory entities.

### 2.3. BOM snapshot at planning time

Freezing the recipe snapshot into the WorkOrder metadata is a strong design decision.

Keep:

- `_recipe_snapshot` in `WorkOrder.meta`
- execution based on the planned recipe snapshot, not the mutable current recipe

This protects historical integrity and makes production close-out auditable.

### 2.4. Ledger + event trail split

`WorkOrderItem` handles material-level traceability and `WorkOrderEvent` handles semantic state mutations. This split is elegant and useful.

Keep both.

### 2.5. Optimistic concurrency + row locking

The package already combines:

- `select_for_update()` for row-level serialization
- `rev` for optimistic concurrency
- `idempotency_key` for duplicate-close protection

This should stay.

---

## 3. Problems vs design decisions

This section is critical. Not every rough edge is a defect. Some are valid design choices that simply need to be made explicit.

### 3.1. External integration failures on `close()` / `void()`

Current behavior:

- Craftsman completes its own transaction
- inventory integration is attempted
- integration failures are logged as warnings and do not abort the WorkOrder transition

Interpretation:

- **not necessarily a bug**
- valid for standalone mode
- unsafe as the default behavior for tightly integrated production mode

Conclusion:

This should be reframed as an **operating mode decision**, not a blanket defect.

### 3.2. Validation helpers that silently skip on unexpected backend errors

Current behavior:

- committed-holds validation may skip
- shared-ingredient validation may skip
- downstream-deficit validation may skip
- many unexpected exceptions are swallowed to preserve standalone behavior

Interpretation:

- acceptable in standalone/graceful mode
- too weak in integrated/strict mode

Conclusion:

Not a pure bug. It needs **mode-aware enforcement**.

### 3.3. BOM recursion depth limit

Current behavior:

- recursive BOM expansion stops after depth > 5
- this is described as cycle protection

Interpretation:

- acceptable as a deliberate simplicity bound for micro-MRP
- insufficient if the package claims generic multilevel BOM support

Conclusion:

Treat this as a **scope limit**, unless general-purpose deep BOM support becomes a goal.

### 3.4. `WorkOrder.code` and `CodeSequence`

Initial reading could treat this as just a local implementation choice. After review, the suite-level architectural question is stronger:

- the identifier is human-readable
- externally visible
- used in API lookup
- used in admin/logs
- used as integration reference

That makes it behave more like a **ref** than a purely local code.

Conclusion:

- not a functional defect
- but likely an **architectural naming mismatch** with the suite convention
- the capability is valid; the current formulation is probably too local

### 3.5. API narrower than kernel

This may or may not be intentional.

Current state:

- service `close()` accepts richer shapes (`produced` list, `wasted` list)
- API serializer only accepts scalar decimal forms

Interpretation:

- may be deliberate progressive exposure
- but currently appears undocumented and asymmetrical

Conclusion:

Treat as a **surface-contract inconsistency** that should be either documented or resolved.

---

## 4. Hardening priorities

### Priority P0 — architecture/contract decisions

These should be decided before low-level polishing.

#### P0.1. Define operational modes explicitly

Introduce two explicit operating modes for Craftsman:

- `graceful` / `standalone`
- `strict` / `integrated`

Recommended semantics:

##### Graceful mode

- backend absence is allowed
- validation helpers may skip
- inventory failures may log warning and not abort
- package remains usable as standalone production ledger

##### Strict mode

- required backends must be present and loadable
- critical validation failures must abort mutations
- inventory sync failure must fail `close()` / `void()` transactionally or via a controlled compensating model

Recommended settings sketch:

```python
CRAFTSMAN = {
    "MODE": "strict",  # or "graceful"
    "INVENTORY_BACKEND": "...",
    "DEMAND_BACKEND": "...",
}
```

This is the single most important hardening move.

#### P0.2. Decide identity convention: `code` vs `ref`

Recommended decision:

- standardize on `ref` for human-readable operational identity across the suite
- treat current `WorkOrder.code` as a transitional field or alias

Target concept:

- `WorkOrder.ref` becomes the canonical external identifier
- lookup, logs, integrations, and UI use `ref`

This aligns Craftsman with the broader suite language.

#### P0.3. Decide shared ref-generation strategy

Recommended direction:

Create a shared utility in `shopman-utils`, such as:

- `RefGenerator`
- `RefFormatter`
- `RefSequencePolicy`

Purpose:

- generate human-readable operational refs
- support multiple domains uniformly
- e.g. `WO-2026-00042`, `ORD-2026-01583`, `PAY-2026-00117`

Recommended structure:

- shared generator logic in `shopman-utils`
- sequence persistence stays local to each app

Do **not** rush into a single global central DB table in `shopman-utils` unless later justified.

---

## 5. Domain hardening actions

### P1. Identity hardening

#### P1.1. Migrate `WorkOrder.code` toward `WorkOrder.ref`

Recommended path:

1. add `ref` field or rename field with compatibility layer
2. keep `code` as alias/property temporarily
3. switch API lookup to `ref`
4. switch admin/list displays/logging to `ref`
5. switch inventory protocol calls to `ref=order.ref`
6. deprecate `code`

If you want a lighter path:

- keep DB column as-is temporarily
- expose canonical semantic name `ref` at model/service/API layer
- treat `code` as backward-compat alias

#### P1.2. Replace `CodeSequence` with app-scoped ref sequence infrastructure

The current capability is useful. The current local abstraction is probably too narrow.

Recommended direction:

- preserve sequential legible identifier generation
- migrate away from Craftsman-specific `CodeSequence`
- use a shared generator contract from `shopman-utils`
- keep persistence local to Craftsman while needed

Possible transitional structure:

- `WorkOrderRefSequence` in Craftsman
- `RefGenerator` in `shopman-utils`

Do **not** remove sequence generation unless you are also deliberately giving up human-readable operational refs.

---

### P2. Integrated-mode reliability hardening

#### P2.1. Make inventory synchronization policy explicit

Current behavior is always non-fatal.

Recommended:

- in graceful mode: keep warning-only behavior
- in strict mode: fail mutation when inventory sync fails

Options for strict mode:

##### Option A — fully transactional sync

- if inventory adapter is local and transaction-compatible, abort `close()` / `void()` on sync failure

##### Option B — outbox/compensation model

- commit Craftsman state
- write durable integration event/outbox record
- mark sync status as pending/failed
- do not pretend the operation is fully complete until sync is reconciled

If you anticipate asynchronous or remote integrations, Option B is structurally stronger.

#### P2.2. Stop swallowing critical exceptions in strict mode

Current helpers should behave differently by mode.

Target behavior:

- graceful mode: keep skip behavior
- strict mode: unexpected backend/integration errors must raise `CraftError`

Apply this to:

- `_validate_committed_holds()`
- `_validate_shared_ingredients()`
- `_validate_downstream_deficit()`
- `_call_inventory_on_close()`
- `_call_inventory_on_void()`

#### P2.3. Make strict dependencies fail early

In strict mode, backend loading should fail at startup or first explicit boot-time validation, not silently later.

Recommended:

- add config validation step in app startup or a dedicated diagnostics check
- verify configured backend classes are importable and protocol-compatible

---

### P3. API contract hardening

#### P3.1. Align HTTP API with kernel capability

Current mismatch:

- service supports richer `close()` shapes
- API serializers only expose scalar forms

Choose one path explicitly:

##### Path A — expand API to match kernel

Support:

- `produced` as decimal or list
- `wasted` as decimal or list
- optional co-products
- optional detailed waste payloads

##### Path B — keep API intentionally narrow

If so:

- document the limitation explicitly
- state that advanced close semantics are service-only/internal for now

Recommendation:

Prefer **Path A** if Craftsman is meant to be a real reusable headless app.

#### P3.2. Normalize naming in API surface

Current package/app naming and URL naming drift should be resolved.

Decide one canonical vocabulary:

- package namespace
- URL namespace
- docs/examples
- serializer/action docs

Then apply consistently.

---

### P4. Data and model hardening

#### P4.1. Version consistency

Current mismatch between package version declarations should be fixed immediately.

Actions:

- align `pyproject.toml` version and `__version__`
- add release checklist item to prevent divergence

This is small but important for trust.

#### P4.2. Strengthen lifecycle constraints where useful

Evaluate whether additional DB-level constraints would help, for example:

- if `status = done`, then `produced is not null`
- if `status = open`, then `finished_at is null`
- if `status = void`, then `produced is null`

Not all of these need to be DB constraints immediately, but they should at least be explicit service invariants and tested.

#### P4.3. Clarify semantics of `WorkOrderItem`

The unified ledger design is good. Hardening should focus on preserving clarity:

- define whether repeated close/reopen flows are impossible by contract
- confirm whether manual extra ledger rows are allowed or forbidden
- decide whether `WorkOrderItem` is exclusively service-written

Recommended stance:

- `WorkOrderItem` should be treated as append-only service-owned ledger
- admin/manual mutation should be tightly constrained or read-only

---

### P5. Query/BOM hardening

#### P5.1. Be explicit that depth limit is a scope boundary

If you keep `max depth 5`, document it as a deliberate simplification.

Do not describe it as full cycle detection if it is actually just a depth cap.

#### P5.2. Future option: real cycle detection

Only if needed later:

- maintain visited path set during recursion
- distinguish true cycle from legitimate deep BOM
- allow configurable max depth separately from cycle detection

This is optional, not urgent.

#### P5.3. Optimize repeated recipe existence checks in `needs()`

`_aggregate()` currently checks whether a recipe exists for each `item_ref`. That may be acceptable at current scale, but it is a likely performance hotspot later.

Possible hardening:

- prefetch active `output_ref` set once
- memoize `has_recipe` per `item_ref`

This is not urgent unless query volume grows.

---

## 6. Security and governance hardening

### P6.1. Add role/capability boundaries

`IsAuthenticated` is not enough for serious production use.

Recommended permissions to separate:

- can view recipes
- can plan work orders
- can adjust work orders
- can close work orders
- can void work orders
- can view cost/consumption detail

This can start as simple app-level permissions and evolve later.

### P6.2. Limit dangerous admin actions

The current admin actions are useful, but operationally sensitive.

Recommended:

- require stronger permission to bulk-close or bulk-void
- add confirmation messaging with expected effects
- optionally disable in strict environments unless explicitly enabled

### P6.3. Audit actor integrity

`actor` currently appears as a free string in events and ledger records.

Recommended:

- define actor format convention, e.g. `user:joao`, `system:api`, `service:planner`
- validate or normalize actor string centrally

---

## 7. Documentation hardening

### P7.1. Add a true package README

The package needs a solid standalone README covering:

- what the app owns and does not own
- standalone mode vs integrated mode
- lifecycle of Recipe and WorkOrder
- how refs work
- how inventory and demand backends plug in
- advanced close semantics

### P7.2. Document identity semantics

Document clearly whether:

- `ref` is the canonical external operational identifier
- `code` is legacy/backward compat
- refs are generated centrally or per app

### P7.3. Document adapter/protocol contracts

The protocols are good. They need practical docs:

- minimal backend implementation example
- strict-mode expectations
- failure semantics
- what methods are best-effort vs authoritative

---

## 8. Testing hardening

### P8.1. Preserve concurrency tests

Existing concurrency tests are strong and should remain.

Keep and expand coverage for:

- duplicate close under PostgreSQL
- stale `expected_rev`
- duplicate void
- adjust/close races
- adjust/void races

### P8.2. Add strict-mode tests

Missing but important:

- inventory backend failure aborts close in strict mode
- backend import failure fails boot or explicit diagnostics in strict mode
- validation helpers raise in strict mode instead of silently passing

### P8.3. Add API contract tests

Test both chosen directions:

- if API stays narrow: assert documented rejection of list forms
- if API expands: assert co-product and detailed waste payloads work end-to-end

### P8.4. Add identity transition tests

If migrating `code` → `ref`, test:

- generation uniqueness
- API lookup by ref
- backward compatibility alias
- integration calls use ref

### P8.5. Add invariant tests

Suggested cases:

- done WO must have `produced`
- void WO cannot be closed later
- second close with same idempotency key is safe
- second close without idempotency key is rejected
- adjust below committed quantity behaves correctly by mode

---

## 9. Recommended phased plan

### Phase 1 — contract cleanup

- align package version declarations
- define `MODE` (`graceful` vs `strict`)
- document current API limitations explicitly
- clean naming drift across package/API/docs

### Phase 2 — identity normalization

- define suite-wide ref policy
- introduce shared ref generator contract in `shopman-utils`
- migrate `WorkOrder.code` toward canonical `WorkOrder.ref`
- maintain backward compatibility temporarily

### Phase 3 — strict integration mode

- make validation helpers mode-aware
- make inventory sync policy mode-aware
- add diagnostics for configured backends
- add strict-mode tests

### Phase 4 — API parity and governance

- expose advanced close semantics over HTTP, or explicitly freeze scope
- add finer-grained permissions
- harden admin bulk actions

### Phase 5 — optional generalization

- upgrade BOM cycle handling if deeper BOM support becomes a goal
- optimize needs/suggest performance if scale requires it

---

## 10. Final recommendation

Craftsman should remain small.

The hardening goal is **not** to make it heavy.
The hardening goal is to make its operating modes, identity semantics, and integration guarantees explicit.

Recommended strategic stance:

- keep the minimal core
- keep the agnostic string-ref approach
- keep ledger + event design
- promote operational identity to canonical `ref`
- extract ref-generation capability to `shopman-utils`
- formalize `graceful` vs `strict` behavior

If that is done, Craftsman can become one of the strongest and cleanest kernels in the Shopman suite.
