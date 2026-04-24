# CONTRACT-CONSOLIDATION-PLAN

Plano de execucao para os 6 achados da analise critica externa
([docs/reports/analise_critica_externa_26-04-24_v1.md](../reports/analise_critica_externa_26-04-24_v1.md)).

Escopo: correcoes contratuais no orquestrador e kernel. Nenhum WP adiciona features.

---

## WP-CC-1: Pricing contract — channel.ref convention

**Goal:** Eliminate the nonexistent `listing_ref` attribute. The convention is `channel.ref == listing.ref`.

**Files:**
- `shopman/shop/handlers/pricing.py` (lines 26, 33)
- `packages/orderman/shopman/orderman/services/modify.py` (line 65)
- `packages/orderman/shopman/orderman/services/commit.py` (line 202)
- `shopman/shop/checks.py` (new check)

**Changes:**

1. **pricing.py** — `OffermanPricingBackend.get_price()`:
   - Line 26: `getattr(customer.group, "listing_ref", None)` — keep as-is (customer groups have their own listing_ref, separate concept).
   - Line 33: `getattr(channel, "listing_ref", None)` — change to `getattr(channel, "ref", None)`. This is the bug: Channel has `ref`, not `listing_ref`. The storefront already uses `channel.ref` correctly.

2. **modify.py** line 65 and **commit.py** line 202: Both create `SimpleNamespace(ref=channel_ref, config={})`. These are already correct — they expose `.ref`, which is what pricing.py should read after the fix. No change needed here.

3. **checks.py** — Add a new deploy check `SHOPMAN_W004` that validates every active `Listing.ref` has a corresponding `Channel.ref` (parity guardrail). Warning-level, not error, since listings can exist without channels (e.g. customer group listings).

**Test criteria:**
- Unit test: `OffermanPricingBackend.get_price()` resolves channel price via `channel.ref` (not `listing_ref`)
- System check test: `SHOPMAN_W004` fires when orphan listing exists without matching channel

**Effort:** S

---

## WP-CC-2: Directive state machine — done vs completed

**Goal:** Replace all `"completed"` status assignments with `"done"`. Add model-level constraint.

**Files:**
- `packages/orderman/shopman/orderman/models/directive.py` (lines 14-25)
- `shopman/shop/handlers/loyalty.py` (lines 45, 58, 65, 84, 110, 125, 137, 152)

**Changes:**

1. **directive.py** — Add status constants to the model:
   ```python
   class Status:
       QUEUED = "queued"
       RUNNING = "running"
       DONE = "done"
       FAILED = "failed"
   ```
   The `choices` field already constrains at form level. Add a `clean()` or `save()` guard that raises `ValueError` if status is not in the valid set, catching ORM bypass of choices validation.

2. **loyalty.py** — Replace all 8 occurrences of `message.status = "completed"` with `message.status = "done"`. These are at lines 45, 58, 65, 84, 110, 125, 137, 152.

3. **Grep verification**: Only `loyalty.py` uses `"completed"`. All other handlers (notification, fulfillment, fiscal, confirmation, returns, accounting, mock_pix, catalog_projection) already use `"done"`.

**Test criteria:**
- Existing loyalty handler tests must pass with `"done"` assertions
- New unit test: `Directive(status="completed").full_clean()` raises `ValidationError`
- New unit test: `Directive.Status.DONE == "done"`

**Effort:** S

---

## WP-CC-3: Retry semantics unification

**Goal:** Handlers should raise exceptions for failure, not mutate directive state directly. The dispatch layer (`dispatch.py:_process_directive`) already handles retry/backoff/failure.

**Files:**
- `packages/orderman/shopman/orderman/dispatch.py` (lines 39-78)
- `shopman/shop/handlers/loyalty.py` — manual attempts/status/last_error mutation (lines 29-31, 37-39, 84-96, 118-120, 152-164)
- `shopman/shop/handlers/notification.py` — manual exhaustion check (lines 80-82, 133-135)
- `shopman/shop/handlers/catalog_projection.py` — manual attempts increment (lines 72-89)
- All other handlers: `fiscal.py`, `fulfillment.py`, `confirmation.py`, `returns.py`, `accounting.py`, `mock_pix.py`

**Changes:**

Phase 1 (this plan):
1. Define two exception types in `packages/orderman/shopman/orderman/exceptions.py`:
   - `DirectiveTerminalError(message, error_code="")` — handler wants immediate failure
   - `DirectiveTransientError(message, error_code="")` — handler wants retry with backoff
   These may already exist; verify and reuse.

2. Update `dispatch.py:_process_directive()` to:
   - On handler return without exception: set `status = "done"`, save.
   - On `DirectiveTerminalError`: set `status = "failed"`, `last_error`, `error_code`, save.
   - On `DirectiveTransientError`: increment attempts, set backoff or fail if max exceeded, save.
   - On any other `Exception`: treat as transient (current behavior).

3. Migrate handlers one at a time. Each handler conversion:
   - Remove all `message.status = ...` / `message.save(...)` / `message.attempts` / `message.last_error` lines.
   - `return` for success (dispatch sets "done").
   - `raise DirectiveTerminalError(...)` for permanent failure (missing payload, order not found).
   - `raise DirectiveTransientError(...)` for retryable failure (adapter timeout).
   - For skip/no-op cases (e.g. no customer, no handle_ref): `return` — these are successful completions.

4. Conversion order (by risk): `loyalty.py` > `notification.py` > `catalog_projection.py` > `fiscal.py` > `fulfillment.py` > `returns.py` > `accounting.py` > `confirmation.py` > `mock_pix.py`.

**Test criteria:**
- Each handler test suite passes after conversion
- Integration test: handler raises `DirectiveTerminalError` -> directive ends as `"failed"`
- Integration test: handler raises `DirectiveTransientError` -> directive re-queued with backoff
- Integration test: handler returns normally -> directive ends as `"done"`
- Zero direct `message.status` assignments remain in `shopman/shop/handlers/`

**Effort:** L

---

## WP-CC-4: Cancellation sequencing

**Goal:** Write cancellation data to `order.data` BEFORE calling `transition_status()`, so that `on_cancelled` lifecycle handlers see the reason.

**Files:**
- `shopman/shop/services/cancellation.py` (lines 50-58)

**Changes:**

1. Invert lines 50-58. Current order:
   ```python
   # Line 50: fires signal → on_commit → lifecycle dispatch
   order.transition_status(Order.Status.CANCELLED, actor=actor)
   # Lines 52-58: writes data AFTER signal is scheduled
   data = dict(order.data or {})
   data["cancellation_reason"] = reason
   ...
   order.save(update_fields=["data", "updated_at"])
   ```
   New order:
   ```python
   # Write data FIRST
   data = dict(order.data or {})
   data["cancellation_reason"] = reason
   data["cancelled_by"] = actor
   if extra_data:
       data.update(extra_data)
   order.data = data
   order.save(update_fields=["data", "updated_at"])

   # THEN transition (fires signal → on_commit → lifecycle with data already present)
   order.transition_status(Order.Status.CANCELLED, actor=actor)
   ```

2. Note: `transition_status()` does `select_for_update().get(pk=self.pk)` then `save()`, which re-reads the row. Since we saved `order.data` first, the locked re-read will have the updated data. The signal fires after the transition save, and `on_commit` runs after that transaction — by which point both data and status are committed.

**Test criteria:**
- Unit test: After `cancel()`, `order.data["cancellation_reason"]` is set
- Integration test: Mock `lifecycle.dispatch` and assert `order.data["cancellation_reason"]` is present when `on_cancelled` fires
- Existing cancellation tests pass

**Effort:** S

---

## WP-CC-5: Orchestrator thickness — ADR only

**Goal:** Document the target architecture for reducing wiring density in `apps.py` and `handlers/__init__.py`. No code changes.

**Files:**
- `shopman/shop/apps.py` (189 lines, 8 methods in `ready()`)
- `shopman/shop/handlers/__init__.py` (303 lines, 16 registration functions)
- `shopman/shop/adapters/__init__.py` (reference)
- New: `docs/decisions/adr-NNN-handler-autodiscovery.md`

**Changes:**

1. Write ADR documenting:
   - **Current state**: `apps.py` calls `register_all()` which has 16 explicit registration functions importing from specific packages. `ALL_HANDLERS` list is a flat manifest but is not used for actual registration (it serves as documentation).
   - **Problem**: Adding a handler requires editing `__init__.py` in two places (ALL_HANDLERS + a `_register_*` function). The orchestrator knows too many package internals.
   - **Target**: Registry/autodiscovery pattern where each handler module exports a `register(registry)` function, and `register_all()` iterates over `ALL_HANDLERS` paths to import and call them. Optional backends use the same pattern with a guard.
   - **Constraints**: Boot order matters (pricing modifiers must register before validators). Signal wiring must remain explicit.
   - **Decision**: Defer implementation to post-production. Document the pattern now so future contributors follow it.

**Test criteria:**
- ADR exists and is linked from `docs/decisions/README.md`
- No code changes

**Effort:** S

---

## WP-CC-6: Webhook security — guestman gate hardening

**Goal:** Guestman G4 gate must reject when secret is empty, matching iFood's pattern.

**Files:**
- `packages/guestman/shopman/guestman/gates.py` (lines 214-225)
- `shopman/shop/webhooks/ifood.py` (lines 144-149, reference pattern)

**Changes:**

1. **gates.py** `provider_event_authenticity()` — Replace the "no secret = skip" block (lines 214-225):
   ```python
   # CURRENT (lines 214-225): accepts all payloads when secret is empty
   if not secret:
       logging.getLogger(__name__).warning(...)
       return GateResult(True, ...)

   # NEW: reject when secret is empty (matches iFood pattern)
   if not secret:
       raise GateError(
           "G4_ProviderEventAuthenticity",
           "Webhook secret is not configured. All requests rejected.",
       )
   ```

2. This matches iFood's `_check_auth()` (lines 144-149) which logs an error and returns `False` when `webhook_token` is empty.

3. Update `check_webhook_tokens` in `shopman/shop/checks.py` to also validate guestman webhook secret is set (add `SHOPMAN_GUESTMAN_WEBHOOK` to the `integrations` list).

**Test criteria:**
- Unit test: `Gates.provider_event_authenticity(body, sig, secret="")` raises `GateError`
- Unit test: `Gates.check_provider_event_authenticity(body, sig, secret="")` returns `False`
- Existing tests that pass empty secret must be updated to expect rejection

**Effort:** S

---

## Execution Order

```
Phase 1 — Quick wins (parallel, no dependencies):
  WP-CC-1  Pricing channel.ref fix           [S] ✅ aec2b8f + c0f63ef
  WP-CC-2  Directive "done" vs "completed"    [S] ✅ 9b12cee
  WP-CC-4  Cancellation sequencing            [S] ✅ 003fe16
  WP-CC-6  Webhook security hardening         [S] ✅ 75a2045

Phase 2 — Requires CC-2 done first:
  WP-CC-3  Retry semantics unification        [L] ✅ 1224590

Phase 3 — Documentation only:
  WP-CC-5  Orchestrator ADR                   [S] ✅ docs/decisions/adr-010-handler-contract-and-autodiscovery.md
```

**PLAN COMPLETE** — All 6 WPs done (2026-04-24).
