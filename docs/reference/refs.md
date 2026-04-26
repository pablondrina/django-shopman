# Refs Optionality

`shopman-refs` is a first-class convenience package for stable human-readable
identifiers, bulk rename/deactivation, and cross-model lookup. The Nelson
Shopman instance installs it and uses its generators for refs such as order
refs and POS tabs.

Kernel apps should not require `shopman-refs` to import or run their core
flows. When a package integrates with refs, the integration must be one of:

- optional `AppConfig.ready()` registration guarded by `ImportError`;
- a `contrib.refs` module that callers opt into;
- a runtime generator with a deterministic local fallback.

Current posture:

- `guestman` and `offerman` register ref types only when `shopman.refs` is installed.
- `orderman.generate_order_ref()` uses `shopman.refs` when available and falls back to a local ref.
- `shop.services.pos` uses `POS_TAB` generation when refs is installed and falls back to a local tab id.
- The root orchestrator may depend on `shopman-refs` for this project, but kernel packages should remain usable without it unless their optional refs integration is explicitly selected.

This keeps refs welcome as infrastructure, not mandatory as a hidden coupling.
