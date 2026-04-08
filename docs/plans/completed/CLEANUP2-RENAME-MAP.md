# CLEANUP2-RENAME-MAP — Namespace rename: old → persona names

> Produced by WP-CL2-9. Execution by WP-CL2-10 (requires explicit approval).
> Created: 2026-04-08

---

## Summary

Python namespaces currently use generic domain names (stocking, ordering,
offering, customers, crafting, payments, auth). Persona names (stockman,
omniman, offerman, guestman, craftsman, payman, doorman) are the project
identity and the name of each package directory. This map bridges the gap.

---

## Old → New Namespace Table

| Package dir       | Python namespace (current) | App label (current) | Python namespace (new) | App label (new) | DB impact |
|-------------------|---------------------------|---------------------|------------------------|-----------------|-----------|
| `packages/stockman/`  | `shopman.stocking`    | `stocking`          | `shopman.stockman`     | `stockman`      | Table rename required |
| `packages/omniman/`   | `shopman.ordering`    | `ordering`          | `shopman.omniman`      | `omniman`       | Table rename required |
| `packages/offerman/`  | `shopman.offering`    | `offering`          | `shopman.offerman`     | `offerman`      | Table rename required |
| `packages/guestman/`  | `shopman.customers`   | `customers`         | `shopman.guestman`     | `guestman`      | Table rename required |
| `packages/craftsman/` | `shopman.crafting`    | `crafting`          | `shopman.craftsman`    | `craftsman`     | Explicit db_table → no change |
| `packages/payman/`    | `shopman.payments`    | `payments`          | `shopman.payman`       | `payman`        | Table rename required |
| `packages/doorman/`   | `shopman.auth`        | `shopman_auth`      | `shopman.doorman`      | `doorman`       | Explicit db_table → no change |

---

## Touch Point Inventory

Total occurrences of `shopman.<old_ns>` across the codebase:

| Namespace         | packages/ | framework/ | instances/ | Total |
|-------------------|-----------|------------|------------|-------|
| `shopman.stocking`  | 174       | 69         | 0          | 243   |
| `shopman.ordering`  | 153       | 183        | 0          | 336   |
| `shopman.offering`  | 141       | 79         | 0          | 220   |
| `shopman.customers` | 260       | 91         | 0          | 351   |
| `shopman.crafting`  | 213       | 41         | 0          | 254   |
| `shopman.payments`  |  42       | 27         | 0          |  69   |
| `shopman.auth`      | 160       | 70         | 0          | 230   |
| **Total**           | **1143**  | **560**    | **0**      | **1703** |

---

## DB Impact Analysis

### Packages with hardcoded `db_table` (SAFE — no rename needed in DB)

- **`shopman.crafting` → `shopman.craftsman`**: All models have explicit `db_table`
  (`crafting_work_order`, `crafting_recipe`, etc.). App label rename from
  `crafting` to `craftsman` only affects Django's internal migration table
  (`django_migrations.app`). Tables themselves don't change.

- **`shopman.auth` → `shopman.doorman`**: All models have explicit `db_table`
  (`shopman_auth_customer_user`, `shopman_auth_trusted_device`, etc.). Same as above.

### Packages WITHOUT hardcoded `db_table` (DB table rename required)

Django auto-names tables as `<app_label>_<model_name>`. Changing `app_label`
changes the auto-generated table name, which requires DB migration with
`AlterModelTable`.

Affected packages:
- `stocking` → `stockman` (tables: `stocking_*` → `stockman_*`)
- `ordering` → `omniman` (tables: `ordering_*` → `omniman_*`)
- `offering` → `offerman` (tables: `offering_*` → `offerman_*`)
- `customers` → `guestman` (tables: `customers_*` → `guestman_*`)
- `payments` → `payman` (tables: `payments_*` → `payman_*`)

**Decision:** Since CLAUDE.md states "migrações serão resetadas no projeto novo"
(migrations will be reset for the new project), the migration strategy is:
reset all migrations with `squashmigrations` or create fresh `0001_initial`
after the rename, rather than adding `AlterModelTable` operations.

---

## Files to Rename (Physical Directory)

```bash
# stockman
mv packages/stockman/shopman/stocking packages/stockman/shopman/stockman

# omniman
mv packages/omniman/shopman/ordering packages/omniman/shopman/omniman

# offerman
mv packages/offerman/shopman/offering packages/offerman/shopman/offerman

# guestman
mv packages/guestman/shopman/customers packages/guestman/shopman/guestman

# craftsman
mv packages/craftsman/shopman/crafting packages/craftsman/shopman/craftsman

# payman
mv packages/payman/shopman/payments packages/payman/shopman/payman

# doorman
mv packages/doorman/shopman/auth packages/doorman/shopman/doorman
```

---

## apps.py Changes

For each package, update `AppConfig`:

```python
# Example: packages/stockman/shopman/stockman/apps.py
class StockmanConfig(AppConfig):
    name = "shopman.stockman"   # was: "shopman.stocking"
    label = "stockman"          # was: "stocking"
```

---

## INSTALLED_APPS in settings.py

```python
# framework/project/settings.py — update to new names
INSTALLED_APPS = [
    ...
    "shopman.utils",
    "shopman.offerman",   # was: "shopman.offering"
    "shopman.stockman",   # was: "shopman.stocking"
    "shopman.craftsman",  # was: "shopman.crafting"
    "shopman.omniman",    # was: "shopman.ordering"
    "shopman.payman",     # was: "shopman.payments"
    "shopman.guestman",   # was: "shopman.customers"
    "shopman.doorman",    # was: "shopman.auth"
    ...
]
```

---

## Idempotent Bash Script

```bash
#!/usr/bin/env bash
# rename-namespaces.sh — idempotent namespace rename
# Usage: bash rename-namespaces.sh [--dry-run]
#
# Requires: GNU sed (macOS: brew install gnu-sed, use gsed)
# On macOS, replace `sed -i` with `sed -i ''` or use gsed.

set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
  DRY_RUN=1
  echo "[DRY RUN] No files will be modified."
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SED_CMD="sed"
# macOS detection
if [[ "$(uname)" == "Darwin" ]]; then
  if command -v gsed >/dev/null 2>&1; then
    SED_CMD="gsed"
  else
    echo "ERROR: Install gnu-sed: brew install gnu-sed" >&2
    exit 1
  fi
fi

# ── Step 1: Rename physical directories ──────────────────────────────────

rename_dir() {
  local from="$1" to="$2"
  if [[ -d "$from" && ! -d "$to" ]]; then
    echo "mv $from → $to"
    [[ $DRY_RUN -eq 0 ]] && mv "$from" "$to"
  elif [[ -d "$to" ]]; then
    echo "SKIP (already renamed): $to"
  else
    echo "SKIP (not found): $from"
  fi
}

rename_dir "$REPO_ROOT/packages/stockman/shopman/stocking"  "$REPO_ROOT/packages/stockman/shopman/stockman"
rename_dir "$REPO_ROOT/packages/omniman/shopman/ordering"   "$REPO_ROOT/packages/omniman/shopman/omniman"
rename_dir "$REPO_ROOT/packages/offerman/shopman/offering"  "$REPO_ROOT/packages/offerman/shopman/offerman"
rename_dir "$REPO_ROOT/packages/guestman/shopman/customers" "$REPO_ROOT/packages/guestman/shopman/guestman"
rename_dir "$REPO_ROOT/packages/craftsman/shopman/crafting" "$REPO_ROOT/packages/craftsman/shopman/craftsman"
rename_dir "$REPO_ROOT/packages/payman/shopman/payments"    "$REPO_ROOT/packages/payman/shopman/payman"
rename_dir "$REPO_ROOT/packages/doorman/shopman/auth"       "$REPO_ROOT/packages/doorman/shopman/doorman"

# ── Step 2: Sed replace imports ──────────────────────────────────────────

replacements=(
  "shopman\.stocking:shopman.stockman"
  "shopman\.ordering:shopman.omniman"
  "shopman\.offering:shopman.offerman"
  "shopman\.customers:shopman.guestman"
  "shopman\.crafting:shopman.craftsman"
  "shopman\.payments:shopman.payman"
  "shopman\.auth:shopman.doorman"
)

TARGETS=(
  "$REPO_ROOT/packages"
  "$REPO_ROOT/framework"
  "$REPO_ROOT/instances"
)

for replacement in "${replacements[@]}"; do
  old="${replacement%%:*}"
  new="${replacement##*:}"
  echo "Replacing: $old → $new"
  if [[ $DRY_RUN -eq 0 ]]; then
    find "${TARGETS[@]}" -name "*.py" -not -path "*/.venv/*" -not -path "*/__pycache__/*" \
      -exec $SED_CMD -i "s/$old/$new/g" {} +
    # Also update non-Python files (pyproject.toml, etc.)
    find "${TARGETS[@]}" -name "*.toml" -o -name "*.cfg" -o -name "*.ini" \
      -not -path "*/.venv/*" \
      | xargs $SED_CMD -i "s/$old/$new/g" 2>/dev/null || true
  fi
done

echo "Done. Run 'make test' to verify."
```

---

## Migration Strategy

Since migrations will be reset for the new production deployment (per CLAUDE.md),
the recommended approach is:

1. Execute the rename.
2. Delete all migration files in each package's `migrations/` folder.
3. Run `python manage.py makemigrations` to generate fresh `0001_initial`
   migrations with the new `app_label`.
4. Run `python manage.py migrate --run-syncdb` on a fresh DB.
5. For existing production DB: use `django_migrations` table manipulation
   or a custom `RunSQL` migration with `ALTER TABLE` statements.

**For this project (new project, no production data yet):** reset is safe.

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| 1703 touch points across 7 packages | High | Idempotent sed script + full test suite |
| DB table rename for 5 packages (no hardcoded db_table) | Medium | Reset migrations (project is pre-production) |
| Cross-package imports (packages import each other) | Medium | Sed replaces all occurrences in one pass |
| apps.py `label` change breaks admin URLs | Low | Admin uses label for URL prefix; update any hardcoded `/admin/<label>/` links |
| Migration history in `django_migrations` table | Medium | Reset approach avoids this entirely |
| pyproject.toml package names | Low | `name = "shopman-stockman"` in pyproject stays; only Python namespace changes |

---

## Execution Order (lowest to highest touch points)

Start with smallest to validate the approach:

1. `shopman.payments` → `shopman.payman` (69 occurrences)
2. `shopman.stocking` → `shopman.stockman` (243)
3. `shopman.offering` → `shopman.offerman` (220)
4. `shopman.crafting` → `shopman.craftsman` (254)
5. `shopman.ordering` → `shopman.omniman` (336)
6. `shopman.auth` → `shopman.doorman` (230)
7. `shopman.customers` → `shopman.guestman` (351)

Run `make test` after each package rename before proceeding to the next.
