# Readiness Report — 2026-04-26

## Scope

Final architecture/readiness pass after the orchestrator refactor work packages
WP-01 through WP-11.

Out of scope by project decision:

- production deployment execution;
- provider/topology decisions;
- committing local helper artifacts such as `ANALYSIS-2026-04-25.md` and
  `start_server.command`.

## Architecture State

- Kernel packages remain independent from host/orchestrator/surface layers.
- Storefront views, APIs, intents, services, and projections now route kernel
  domain reads/commands through `shopman.shop.services.*`.
- Backstage views delegate POS, KDS, production, and order lifecycle commands to
  shop-level services.
- `Channel.kind` and concrete `Flow` classes are not runtime concepts in active
  code. Remaining `Flow` strings are unrelated names such as ManyChat
  `sendFlow`, `CashFlowSummary`, and E2E test labels.
- `shopman-refs` is documented as first-class but optional for kernel packages;
  POS tab generation now has a local fallback when refs is unavailable.

## Canonical Shop Services Added

- `catalog_context`: catalog/listing/product/availability read boundary.
- `catalog_exports`: neutral catalog export contract for future Google,
  WhatsApp, Meta/IG adapters.
- `customer_context`: customer/address/loyalty/consent/preference read boundary.
- `customer_orders`: customer-facing order history, reorder, cancellation, and
  payment command/read boundary.
- `order_tracking`, `order_confirmation`, `payment_status`: customer-facing
  read models for tracking, confirmation, and payment.
- `storefront_context`: storefront pricing, happy hour, minimum order, freshness,
  popular SKU, and upsell context moved to the orchestrator.

## Documentation And Hygiene

- Active docs were updated to the current split and URL vocabulary.
- Obsolete `WP-R3` TODOs were removed by consolidating KDS dispatch into
  `shopman.shop.services.kds` and removing obsolete notification-template cache
  TODO code.
- Portuguese test residue `test_pedido_confirm.py` was renamed to
  `test_order_confirm.py`.
- Bare `except Exception: pass` in production code was removed or made
  observable with debug logging.
- Pre-deploy checklist was added at `docs/predeploy/security-readiness.md`.
- Refs optionality was added at `docs/reference/refs.md`.
- The `fresh_from_oven` dynamic collection was aligned with the current
  Craftsman contract: `status=finished`, `finished_at`, and `output_sku`.

## Security Readiness

`python manage.py check` currently passes with one expected local warning:

- `SHOPMAN_W001`: SQLite is configured locally. Production must use PostgreSQL.

`python manage.py check --deploy` runs and surfaces expected local/development
warnings, primarily:

- local SQLite;
- `DEBUG=True` in the current environment;
- local weak/default secret key;
- secure cookie/HSTS/SSL redirect warnings caused by local debug settings;
- drf-spectacular serializer/schema warnings for API documentation.

These are documented in `docs/predeploy/security-readiness.md`. The production
criterion is still: run `manage.py check --deploy` with `DJANGO_DEBUG=false`,
explicit hosts, production secrets, webhook tokens, and PostgreSQL.

## Omotenashi/Mobile/WhatsApp Surfaces

Reviewed and kept intact:

- menu/catalog/PDP product card state;
- cart drawer/page minimum-order and upsell context;
- checkout auth, saved address, pickup slot, loyalty and payment path;
- login/OTP/trusted-device flow;
- order tracking/reorder/payment/confirmation;
- Backstage POS/KDS/order lifecycle surfaces.

No broad UI redesign was made. The work was architectural and read-model
focused, with small behavior-preserving routing changes only.

## Validation Commands

Commands run during this pass:

```bash
python manage.py check
python manage.py check --deploy
ruff check .
pytest -q shopman/shop/tests/test_import_boundaries.py
pytest -q shopman/shop/tests/test_dynamic_collections.py
pytest -q shopman/storefront/tests/test_happy_hour_badge.py \
  shopman/storefront/tests/web/test_projections_cart.py \
  shopman/storefront/tests/web/test_projections_catalog.py \
  shopman/storefront/tests/web/test_projections_product_detail.py \
  shopman/storefront/tests/web/test_web_checkout.py
pytest -q
```

Surface smoke run with Django `Client` and local `ALLOWED_HOSTS` override:

```text
/ 200
/menu/ 200
/cart/ 200
/checkout/ 302 /cart/
/login/ 200
/conta/ 404
/gestor/ 404
/gestor/pos/ 302 /admin/login/?next=/gestor/pos/
/gestor/kds/ 302 /admin/login/?next=/gestor/kds/
```

Final full-suite result for this pass:

```text
709 passed, 11 skipped, 1 warning
```

## Remaining Pre-Deploy Items

These are not architecture debts; they are environment/deploy decisions:

- PostgreSQL database and backup/restore process.
- Final domains for Storefront, Backstage, and webhooks.
- `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`.
- Real payment adapters for enabled payment methods.
- Webhook tokens/secrets for EFI, iFood, Stripe, and ManyChat.
- Logging/monitoring destination and webhook failure alerting.
- Decision on API schema warnings if public OpenAPI documentation is required.
