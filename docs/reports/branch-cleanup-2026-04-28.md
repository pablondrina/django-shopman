# Branch cleanup 2026-04-28

Backup created before cleanup:

`/.git/codex-backups/branch-cleanup-2026-04-28/legacy-claude-branches.bundle`

## Harvested

- `claude/elegant-fermat-49ca69` / HP2-07: harvested only the clean part that still mattered.
  - `shopman.shop.services.customer.SkipAnonymous` is now public for instance strategies.
  - `instances.nelson.customer_strategies` no longer imports private customer-service helpers.
  - Nelson keeps the current `pdv` naming and current single seed command.

## Superseded By Main

The following branches were reviewed and intentionally not cherry-picked because `main`
already contains the behavior in a newer shape, or the old branch would reintroduce
pre-split paths, duplicate migrations, duplicate tests, or stale naming.

- `claude/recursing-matsumoto-9aae2e` / HP2-01: Orderman admin/API fix already present.
- `claude/keen-chatelet-33d19b` / HP2-02: Doorman rename already present; old conflict tried to regress logout handling.
- `claude/dreamy-rubin-ac8917` and `origin/hp2-03-guestman-fixes` / HP2-03: Guestman hardening already present in newer form; remote orphan attempted stale template/API shapes.
- `claude/laughing-edison-05cf48` / HP2-04: Offerman projection metadata, retract behavior, and tests already present.
- `claude/admiring-sanderson-c88f73` / HP2-05: Stockman queryset guards, channel scope resolver, planning disambiguation, and tests already present.
- `claude/quizzical-shamir-dc656a` / HP2-06: Payman gateway uniqueness, cancel reason, expiry, and transaction immutability already present.
- `claude/peaceful-greider-bc445a` / HP2-08: Tracking projection/constants work already present after storefront split.
- `claude/blissful-hofstadter-7a3767` / HP2-09: Utils admin/phone fixes already present.
- `claude/crazy-khorana-61d613`: `CommitResult` is already a frozen dataclass and callers use attributes.
- `claude/affectionate-buck-ac93a0`: cart intents already exist in a cleaner request-free shape.
- `wp-gap-14-availability-substitutes-ux`: stock-error modal variants, substitutes, planned stock, and Kintsugi copy already present in storefront.
- `claude/strange-herschel-3289a5`: operator feedback/toasts/sounds already present in Backstage orders.
- `claude/relaxed-bardeen-fa5d6a`: explicit device trust and skip-OTP flow already present.
- `claude/nice-khorana-befa47`: Omotenashi Portao 2 partials already present in newer UI.
- `claude/loving-jones-e616c6`: six commits were patch-equivalent to `main`; the remaining M4 flow is already present via `access_urls.py` and `test_access_urls.py`.
- `claude/nice-pasteur-544000`: old two-zone order manager is superseded by the current Entrada/Preparo/Saida queue.
- `claude/youthful-hellman-738e3f`: architecture guardrails are present in `test_architecture.py`, `test_import_boundaries.py`, and `test_no_deep_kernel_imports.py`.
- `claude/determined-gates-d6a642` and `claude/sweet-shtern-d9063e`: adapter/surface split already present.
- `claude/elastic-wing` and `claude/naughty-herschel`: stale pre-rename/P0 cleanup already reflected in current tree.
- `claude/compassionate-turing` and `claude/recursing-boyd`: old storefront UI sprint work is superseded by the current storefront.

## Local-only Branches Preserved In Bundle Before Deletion

- `claude/affectionate-buck-ac93a0`
- `claude/crazy-khorana-61d613`
- `claude/loving-jones-e616c6`
- `claude/sweet-shtern-d9063e`
- `claude/youthful-hellman-738e3f`
- `wp-gap-14-availability-substitutes-ux`

## Remote-only Branch Preserved In Bundle Before Deletion

- `origin/hp2-03-guestman-fixes`
