# Storefront persona E2E — findings

Exploratory end-to-end stress tests driving the real storefront JSON API
(`/api/v1/...`) through the Django test client, one complete journey per persona
(browse → cart → checkout → payment → tracking). Business rules, stock holds,
pricing modifiers, payment intents and the order lifecycle all run for real; only
the outbound gateways are the in-repo mock/console adapters.

Files (mine): `test_persona_1_anonymous.py` … `test_persona_6_bundle_promo.py`,
shared helpers in `_journey.py`, fixtures in `conftest.py`.

Result: **29 passed, 2 xfailed** (the 2 xfails pin real defects — see below).

> Note: two other files in this directory (`test_business_rules_edge_cases.py`,
> `test_omotenashi_audit.py`) were **not** authored here — they appeared during
> the session, apparently from a concurrent session, and were left untouched.

---

## Real defects found

### 1. Card checkout on the `web` channel returns HTTP 400 and orphans an order  — **HIGH**

Pinned by `test_persona_2_loyal.py::test_card_checkout_on_web_is_broken` (xfail, strict).

A plain card checkout on the storefront (`payment_method="card"`, `web` channel
with the production seed config: `payment.timing = "post_commit"`) fails:

```
POST /api/v1/checkout/ {payment_method: "card", ...}
→ 400 {"detail":"Campos selados não podem ser alterados: snapshot",
       "error_code":"sealed_field_modified"}
… while the order IS committed to the DB (status "new").
```

Cause: for `post_commit` timing, `_should_initiate_payment_on_commit` returns
True for card (`shop/lifecycle.py`), so `payment.initiate()` runs **inside the
on-commit dispatch** on the same sealed order instance. `_persist_intent`
(`shop/services/payment.py`) then calls `order.save(update_fields=["data",...])`,
and the `Order` seal check (`orderman/models/order.py`) trips on `snapshot`.

Reproduced three ways — a standalone autocommit script, a `transaction=True`
pytest, and the direct HTTP path — so it is **not** a test-transaction artifact.
PIX and cash are unaffected: PIX is `post_commit` and initiates from a
freshly-loaded order later (via `GET /payment`), which recaptures the seal
baseline; card initiates from the commit-time instance.

Customer impact: a customer choosing card sees an error while an order is left
behind. Suggested direction: initiate card payment from a re-loaded/locked order
inside the dispatch (as PIX does), or defer card initiation off the commit
instance.

### 2. Group-scoped (loyalty/staff) coupon is accepted but discounts nothing — **MEDIUM**

Pinned by `test_persona_2_loyal.py::test_group_coupon_should_discount_for_member`
(xfail, strict).

A coupon whose promotion is scoped to a `customer_segment` / group (e.g. a
"fiéis" loyalty coupon) is **accepted** at apply-time (`POST /cart/coupon/` →
200, `coupon_code` stored) for an eligible member, but strikes **zero** discount:

```
FIEL10 (10% off, customer_segments=["fieis"]), member of "fieis":
  apply → 200, cart.coupon_code == "FIEL10", cart.coupon_discount_q == 0
```

Cause: two different sources of the customer's group. The eligibility gate
(`storefront/cart.py::_customer_eligible_for_promo`) reads `customer.group.ref`
directly, so it passes. But the discount modifier
(`DiscountModifier._matches`) reads the group from the pricing **context**, and
the storefront never populates `customer_group` in the cart pricing context
(only the POS writes `customer.group` into the session). So the segment match
fails and the discount is 0. There is also a noisy
`Customer has no insight` traceback logged from the same path.

Customer impact: "coupon applied" with no money off — worse than a clear refusal.
An **open** (non-segmented) coupon works correctly
(`test_open_loyalty_coupon_applies_discount` passes: R$3,00 off).

---

## Boundary confirmed (not a bug, worth stating)

### Employee discount is POS-only — unreachable from the storefront

`test_persona_3_employee.py`. The employee discount fires only when
`session.data["customer"]["group"] == "staff"`, which **only the POS**
attach-customer path writes. The storefront hardcodes the `web` channel and
writes only `{name, phone}`, so a staff member ordering on the public store pays
full price (correct — the public store must not leak staff pricing). The
mechanism itself is verified at the modifier level (20% off when the session
carries the staff group). Persona 3 as literally specified ("counter, channel=
counter, PIN") is a backstage/POS concern, not a storefront journey.

---

## Behaviour characterised while writing the suite (expected, documented for clarity)

- **Preorder is first-class on `web`.** A future-dated commit is accepted even
  with no batch planned; it registers a **demand** hold (`quant=None`, indefinite)
  for the target date rather than refusing. With a batch planned for the exact
  date, the hold binds to a **planned** Quant. (`test_persona_4_preorder.py`.)
- **Perishable = function of *when*.** `shelf_life_days == 0` items are only
  promisable from a batch planned for that exact day; non-perishable stock covers
  any future date. A product with **zero Quants** is treated as *untracked* and
  sold with no hold at all (no production signal) — fine for truly untracked
  SKUs, but worth noting for made-to-order items seeded without any plan.
- **Preorder rejections are calendar-based**, enforced server-side at commit:
  closed day ("Estamos fechados nesse dia"), past date, and beyond
  `max_preorder_days` all return 400 with `field: delivery_date`.
- **Delivery fee** resolves via `DeliveryZone` (CEP-prefix override), previews in
  the checkout draft, becomes a real `__DELIVERY_FEE__` order line and enters
  `total_q`. An `exclude` zone blocks the commit; delivery requires both an
  address and a date. (`test_persona_5_delivery.py`.)
- **Bundle availability = min(components)**; a component with no stock makes the
  bundle `unavailable` / not addable (409). **Automatic** (coupon-less)
  promotions strike the catalogue price; a manual coupon does **not** stack on
  top of a bigger automatic promo on the same line ("biggest wins").
  (`test_persona_6_bundle_promo.py`.)
- **Anonymous checkout works** even though the checkout projection advertises
  `requires_authentication: true` for `web` — the POST endpoint itself does not
  enforce login. Persona 1 logs in by OTP (the intended flow) and the customer is
  materialised at/after commit. The gate is client-side only; not necessarily a
  bug, but a mismatch worth knowing.

---

## Harness notes (for anyone extending these)

- pytest-django forces `settings.DEBUG=False`, which disables the "simulate
  payment" action. Digital-payment journeys opt in with
  `@override_settings(SHOPMAN_ALLOW_MOCK_PAYMENT_ADAPTERS=True)` (the staging flag).
- Loyalty **redeem debit** happens via a `loyalty.redeem` directive emitted from
  the on-commit dispatch. Django test transactions don't run `on_commit`
  callbacks, so use `J.checkout_committed(client, django_capture_on_commit_callbacks, …)`
  to see the ledger actually debited.
- Today-pickup slots depend on wall clock + closing time; use the **last** slot
  (`J.last_pickup_slot()`) for today or any slot for a future date to stay
  time-stable.
