"""
Availability service — canonical sync API for stock checks and reservations.

This is the FIRST-CLASS service for "can the customer order this?" across all
channels (storefront cart, POS, totem, marketplace inbound). It wraps:

- Stockman.availability (read) — orderable/reserved/breakdown by SKU and channel
- adapters.stock.create_hold (write) — actual hold creation in Stockman
- services.alternatives.find (suggest) — fallback alternatives on shortage

Three verbs:

    check(sku, qty, *, channel_ref) -> dict
        Read-only. Returns whether `qty` of `sku` can be ordered now.

    reserve(sku, qty, *, session_key, channel_ref, ttl_minutes=30) -> dict
        Write. Checks first; if available, creates a hold tagged with session_key
        as `reference` so the order's CommitService can adopt it. On shortage,
        populates `alternatives` with suggested SKUs.

    reconcile(sku, new_qty, *, session_key, channel_ref, ttl_minutes=30) -> dict
        Write. Brings the total reserved quantity for `(session_key, sku)` to
        exactly `new_qty`. Grows by creating a fresh hold for the delta (may
        shortage); shrinks by releasing holds FIFO and creating a compensating
        hold for any release overshoot; `new_qty=0` releases everything.

All three return plain dicts so callers (cart UX, marketplace flow, API) can
react without coupling to Stockman internals.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.adapters import get_adapter
from shopman.omniman.models import Channel

from . import alternatives

logger = logging.getLogger(__name__)


def check(sku: str, qty: Decimal, *, channel_ref: str | None = None) -> dict:
    """
    Read-only availability check for a single SKU/qty in a channel scope.

    If the SKU is a bundle, expands it via CatalogService.expand() and runs
    check() recursively for each component. Returns ok=False at the first
    failing component (with failed_sku identifying it) or ok=True with
    available_qty = min constructable bundles if all components pass.

    Validations applied for simple SKUs (in order):
      1. Channel listing membership — if `channel_ref` is provided and the
         channel has a `listing_ref`, the SKU must be in that listing as a
         published+available `ListingItem`. Otherwise → ok=False, error_code=
         "not_in_listing". This catches marketplace orders pushing SKUs that
         the merchant doesn't actually offer on that channel.
      2. Stockman availability — Offerman global pause (`is_paused`),
         per-channel safety_margin and allowed_positions, plus physical
         stock breakdown.

    Returns:
        {
            "ok": bool,                 # passes listing check AND stock check
            "available_qty": Decimal,   # total_orderable for this channel
            "is_paused": bool,          # product paused/unpublished
            "is_planned": bool,         # only future quants exist
            "breakdown": {ready, in_production, d1},
            "error_code": str | None,   # set when ok=False
            "is_bundle": bool,          # True when SKU is a bundle
            "failed_sku": str | None,   # component that caused failure (bundles only)
        }
    """
    qty_d = Decimal(str(qty))

    # ── 0) Bundle expansion ─────────────────────────────────────────────────
    components = _expand_if_bundle(sku, qty_d)
    if components is not None:
        return _check_bundle(sku, qty_d, components, channel_ref=channel_ref)

    # ── 1) Channel listing membership ───────────────────────────────────────
    listing_item = _sku_in_channel_listing(sku, channel_ref)
    if listing_item is False:
        return {
            "ok": False,
            "available_qty": Decimal("0"),
            "is_paused": False,
            "is_planned": False,
            "breakdown": {"ready": Decimal("0"), "in_production": Decimal("0"), "d1": Decimal("0")},
            "error_code": "not_in_listing",
            "is_bundle": False,
            "failed_sku": None,
        }

    # Check min_qty constraint from listing
    if listing_item is not None and listing_item is not True:
        min_qty = listing_item.get("min_qty") if isinstance(listing_item, dict) else None
        if min_qty is not None and qty_d < Decimal(str(min_qty)):
            return {
                "ok": False,
                "available_qty": Decimal(str(min_qty)),
                "is_paused": False,
                "is_planned": False,
                "breakdown": {"ready": Decimal("0"), "in_production": Decimal("0"), "d1": Decimal("0")},
                "error_code": "below_min_qty",
                "is_bundle": False,
                "failed_sku": None,
            }

    # ── 2) Stockman availability ────────────────────────────────────────────
    adapter = get_adapter("stock")
    scope = adapter.get_channel_scope(channel_ref)
    info = adapter.get_availability(
        sku,
        safety_margin=scope["safety_margin"],
        allowed_positions=scope["allowed_positions"],
    )

    available = info["total_orderable"]
    is_paused = info.get("is_paused", False)

    # If Stockman has no data at all for this SKU (no positions, not paused),
    # the product is outside the stock subsystem's scope — treat as available.
    # This matches the prior NoopStockBackend behavior and keeps Offerman-only
    # products (test fixtures, drop-shipped items) addable to the cart.
    if not is_paused and not info.get("positions"):
        return {
            "ok": True,
            "available_qty": Decimal("999999"),
            "is_paused": False,
            "is_planned": False,
            "breakdown": info.get("breakdown", {}),
            "untracked": True,
            "is_bundle": False,
            "failed_sku": None,
        }

    ok = (not is_paused) and qty_d <= available
    error_code = None
    if not ok:
        error_code = "paused" if is_paused else "insufficient_stock"

    return {
        "ok": ok,
        "available_qty": available,
        "is_paused": is_paused,
        "is_planned": info.get("is_planned", False),
        "breakdown": info.get("breakdown", {}),
        "error_code": error_code,
        "is_bundle": False,
        "failed_sku": None,
    }


def _expand_if_bundle(sku: str, qty: Decimal) -> list[dict] | None:
    """Return component list if SKU is a bundle, None if it's a simple product.

    Returns None (not a bundle) when expand_bundle raises any error,
    including NOT_A_BUNDLE and SKU_NOT_FOUND — callers handle missing SKU
    via the Stockman gate.
    """
    try:
        catalog = get_adapter("catalog")
        components = catalog.expand_bundle(sku, qty)
        # Guard: if expand returns a single component with the same SKU, treat
        # as simple product (infinite recursion prevention).
        if len(components) == 1 and components[0]["sku"] == sku:
            return None
        return components
    except Exception:
        return None


def _check_bundle(
    bundle_sku: str,
    bundle_qty: Decimal,
    components: list[dict],
    *,
    channel_ref: str | None,
) -> dict:
    """Check availability of all bundle components recursively.

    Returns ok=False at the first failing component, or ok=True with
    available_qty = number of full bundles constructable from components.
    """
    min_constructable: Decimal | None = None

    for comp in components:
        comp_sku = comp["sku"]
        comp_qty = Decimal(str(comp["qty"]))

        result = check(comp_sku, comp_qty, channel_ref=channel_ref)

        if not result["ok"]:
            return {
                "ok": False,
                "available_qty": result["available_qty"],
                "is_paused": result.get("is_paused", False),
                "is_planned": result.get("is_planned", False),
                "breakdown": result.get("breakdown", {}),
                "error_code": result.get("error_code"),
                "is_bundle": True,
                "failed_sku": comp_sku,
            }

        # Calculate how many bundles we can build from this component's stock.
        # comp["qty"] is already comp_qty_per_bundle * bundle_qty (because
        # CatalogService.expand multiplies by qty). To get per-bundle qty,
        # divide back: comp_qty_per_bundle = comp_qty / bundle_qty.
        comp_qty_per_bundle = comp_qty / bundle_qty if bundle_qty else comp_qty
        if comp_qty_per_bundle > 0:
            constructable = result["available_qty"] / comp_qty_per_bundle
        else:
            constructable = Decimal("0")

        if min_constructable is None or constructable < min_constructable:
            min_constructable = constructable

    return {
        "ok": True,
        "available_qty": min_constructable if min_constructable is not None else Decimal("0"),
        "is_paused": False,
        "is_planned": False,
        "breakdown": {},
        "error_code": None,
        "is_bundle": True,
        "failed_sku": None,
    }


def _sku_in_channel_listing(sku: str, channel_ref: str | None) -> dict | bool:
    """Return listing item dict when the SKU is published+available in the channel's listing.

    Returns True when the check is skipped (no channel_ref or no listing_ref),
    False when the SKU fails the listing gate.

    Callers treat True as "gate skipped", a dict as "gate passed with item data"
    (used for min_qty checks), and False as "gate failed".

    If the channel has no `listing_ref` configured, the check is skipped
    (returns True) — this preserves backward compatibility for channels that
    don't constrain their catalog (e.g. internal POS).
    """
    if not channel_ref:
        return True

    try:
        channel = Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist:
        return True

    listing_ref = channel.ref
    if not listing_ref:
        return True

    # Gate is only active when a Listing with this ref actually exists.
    # Convention: listing.ref == channel.ref, but listing may not be configured.
    catalog = get_adapter("catalog")
    if not catalog.listing_exists(listing_ref):
        return True

    item = catalog.get_listing_item(sku, listing_ref)
    if item is None:
        return False
    return item


def reserve(
    sku: str,
    qty: Decimal,
    *,
    session_key: str,
    channel_ref: str | None = None,
    ttl_minutes: int = 30,
) -> dict:
    """
    Inline check + hold creation for the storefront/POS/marketplace flows.

    On success: creates a Stockman hold tagged with `reference=session_key` so
    the eventual CommitService can adopt the holds when the order is created.

    On shortage or pause: returns ok=False with `alternatives` populated via
    services.alternatives.find().

    Returns:
        {
            "ok": bool,
            "hold_id": str | None,
            "available_qty": Decimal,
            "is_paused": bool,
            "error_code": str | None,    # only when ok=False
            "alternatives": list[dict],  # only when ok=False
        }
    """
    qty_d = Decimal(str(qty))
    status = check(sku, qty_d, channel_ref=channel_ref)

    # SKUs that are not tracked by Stockman: skip the hold (the order will
    # commit without stock reservation, same as the legacy noop path).
    if status.get("untracked"):
        return {
            "ok": True,
            "hold_id": None,
            "available_qty": status["available_qty"],
            "is_paused": False,
            "error_code": None,
            "alternatives": [],
        }

    if not status["ok"]:
        return {
            "ok": False,
            "hold_id": None,
            "available_qty": status["available_qty"],
            "is_paused": status["is_paused"],
            "error_code": status.get("error_code") or (
                "paused" if status["is_paused"] else "insufficient_stock"
            ),
            "alternatives": alternatives.find(sku, qty=qty_d, channel=channel_ref),
        }

    adapter = get_adapter("stock")

    # For bundles: create one hold per component (not one hold for the bundle SKU).
    if status.get("is_bundle"):
        components = _expand_if_bundle(sku, qty_d)
        if components:
            return _reserve_bundle_components(
                sku, qty_d, components,
                session_key=session_key,
                ttl_minutes=ttl_minutes,
                channel_ref=channel_ref,
                available_qty=status["available_qty"],
                adapter=adapter,
            )

    result = adapter.create_hold(
        sku=sku,
        qty=qty_d,
        ttl_minutes=ttl_minutes,
        reference=session_key,
    )

    if not result.get("success"):
        # Race: stock vanished between check and hold. Surface as shortage.
        logger.info(
            "availability.reserve: hold failed sku=%s qty=%s code=%s",
            sku, qty_d, result.get("error_code"),
        )
        return {
            "ok": False,
            "hold_id": None,
            "available_qty": status["available_qty"],
            "is_paused": False,
            "error_code": result.get("error_code", "hold_failed"),
            "alternatives": alternatives.find(sku, qty=qty_d, channel=channel_ref),
        }

    return {
        "ok": True,
        "hold_id": result["hold_id"],
        "available_qty": status["available_qty"],
        "is_paused": False,
        "error_code": None,
        "alternatives": [],
    }


def reconcile(
    sku: str,
    new_qty: Decimal,
    *,
    session_key: str,
    channel_ref: str | None = None,
    ttl_minutes: int = 30,
) -> dict:
    """
    Bring the total reserved qty for `(session_key, sku)` to exactly `new_qty`.

    Used by the cart's stepper and remove flows: while `reserve()` assumes a
    brand-new additive reservation, `reconcile()` computes the delta against
    the session's existing holds for the SKU and adjusts accordingly.

    Grow (`new_qty > current`):
        Runs `check()` first; creates a hold for `(new_qty - current)`. On
        shortage or hold failure, returns `ok=False` with alternatives and
        leaves existing holds untouched.

    Shrink (`new_qty < current`):
        Releases holds FIFO until the released qty covers the diff. If the
        last released hold overshoots, creates a small compensating hold for
        the overshoot so the final reserved qty lands on `new_qty`.

    Zero (`new_qty == 0`):
        Releases every hold for the SKU in this session.

    No-op (`new_qty == current`):
        Returns immediately with `ok=True`.

    Bundles are expanded via `CatalogService.expand()` and reconciled per
    component (each component is tracked as a separate hold).

    Returns:
        {
            "ok": bool,
            "hold_ids": list[str],       # newly created hold_ids (grow/shrink-overshoot)
            "released_ids": list[str],   # released hold_ids (shrink)
            "available_qty": Decimal,    # only meaningful on shortage
            "is_paused": bool,
            "error_code": str | None,
            "alternatives": list[dict],
        }
    """
    new_qty_d = Decimal(str(new_qty))
    if new_qty_d < 0:
        new_qty_d = Decimal("0")

    # Bundles are reconciled per component, but ONLY for grow (new_qty>0) —
    # shrink/zero for bundles is delegated to commit-time leftover release
    # via `services.stock.hold`, because per-component shrink could
    # over-release holds when the SKU is shared with another cart line.
    if new_qty_d > 0:
        components = _expand_if_bundle(sku, new_qty_d)
        if components is not None:
            return _reconcile_bundle_components(
                sku, new_qty_d, components,
                session_key=session_key,
                channel_ref=channel_ref,
                ttl_minutes=ttl_minutes,
            )
    else:
        # new_qty == 0 on a potential bundle: check if it's actually a bundle
        # to avoid touching shared-component reservations.
        probe = _expand_if_bundle(sku, Decimal("1"))
        if probe is not None:
            logger.info(
                "availability.reconcile: skipping release for bundle %s "
                "(deferred to commit-time leftover release)",
                sku,
            )
            return {
                "ok": True,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": Decimal("0"),
                "is_paused": False,
                "error_code": None,
                "alternatives": [],
            }

    return _reconcile_simple(
        sku, new_qty_d,
        session_key=session_key,
        channel_ref=channel_ref,
        ttl_minutes=ttl_minutes,
    )


def _load_session_holds_for_sku(
    session_key: str, sku: str,
) -> list[tuple[str, Decimal]]:
    """Return FIFO list of `(hold_id, qty)` for active session holds on `sku`."""
    adapter = get_adapter("stock")
    holds = adapter.find_holds_by_reference(session_key, sku=sku)
    return [(hold_id, qty) for hold_id, _sku, qty in holds]


def _reconcile_simple(
    sku: str,
    new_qty: Decimal,
    *,
    session_key: str,
    channel_ref: str | None,
    ttl_minutes: int,
) -> dict:
    """Reconcile a simple (non-bundle) SKU to `new_qty`."""
    existing = _load_session_holds_for_sku(session_key, sku)
    current_total = sum((q for _, q in existing), Decimal("0"))

    if new_qty == current_total:
        return {
            "ok": True,
            "hold_ids": [],
            "released_ids": [],
            "available_qty": Decimal("0"),
            "is_paused": False,
            "error_code": None,
            "alternatives": [],
        }

    adapter = get_adapter("stock")

    # ── Grow ──
    if new_qty > current_total:
        delta = new_qty - current_total
        status = check(sku, delta, channel_ref=channel_ref)

        if status.get("untracked"):
            # SKU outside Stockman scope — no hold needed, treat as ok.
            return {
                "ok": True,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": status["available_qty"],
                "is_paused": False,
                "error_code": None,
                "alternatives": [],
            }

        if not status["ok"]:
            return {
                "ok": False,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": status["available_qty"],
                "is_paused": status.get("is_paused", False),
                "error_code": status.get("error_code") or "insufficient_stock",
                "alternatives": alternatives.find(sku, qty=delta, channel=channel_ref),
            }

        result = adapter.create_hold(
            sku=sku,
            qty=delta,
            ttl_minutes=ttl_minutes,
            reference=session_key,
        )
        if not result.get("success"):
            logger.info(
                "availability.reconcile: grow hold failed sku=%s delta=%s code=%s",
                sku, delta, result.get("error_code"),
            )
            return {
                "ok": False,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": status["available_qty"],
                "is_paused": False,
                "error_code": result.get("error_code", "hold_failed"),
                "alternatives": alternatives.find(sku, qty=delta, channel=channel_ref),
            }
        return {
            "ok": True,
            "hold_ids": [result["hold_id"]],
            "released_ids": [],
            "available_qty": status["available_qty"],
            "is_paused": False,
            "error_code": None,
            "alternatives": [],
        }

    # ── Shrink ──
    diff = current_total - new_qty
    released_ids: list[str] = []
    released_qty = Decimal("0")
    for hid, hqty in existing:
        if released_qty >= diff:
            break
        released_ids.append(hid)
        released_qty += hqty

    if released_ids:
        adapter.release_holds(released_ids)

    overshoot = released_qty - diff
    created_ids: list[str] = []
    if overshoot > 0:
        # Stock just went back into the pool; re-reserve the excess so the
        # final total matches new_qty exactly.
        result = adapter.create_hold(
            sku=sku,
            qty=overshoot,
            ttl_minutes=ttl_minutes,
            reference=session_key,
        )
        if result.get("success"):
            created_ids.append(result["hold_id"])
        else:
            logger.warning(
                "availability.reconcile: compensating hold failed sku=%s "
                "overshoot=%s code=%s — session now under-reserved",
                sku, overshoot, result.get("error_code"),
            )

    return {
        "ok": True,
        "hold_ids": created_ids,
        "released_ids": released_ids,
        "available_qty": Decimal("0"),
        "is_paused": False,
        "error_code": None,
        "alternatives": [],
    }


def _reconcile_bundle_components(
    bundle_sku: str,
    bundle_qty: Decimal,
    components: list[dict],
    *,
    session_key: str,
    channel_ref: str | None,
    ttl_minutes: int,
) -> dict:
    """Reconcile each bundle component independently.

    If any grow-step fails, rolls back by releasing newly created holds
    (shrink-steps already applied are not undone — they freed stock that
    is now back in the pool).
    """
    created_ids: list[str] = []
    released_ids: list[str] = []
    adapter = get_adapter("stock")

    for comp in components:
        comp_sku = comp["sku"]
        comp_qty = Decimal(str(comp["qty"]))

        result = _reconcile_simple(
            comp_sku, comp_qty,
            session_key=session_key,
            channel_ref=channel_ref,
            ttl_minutes=ttl_minutes,
        )
        if not result["ok"]:
            # Rollback: release any new holds we've created for previous components.
            if created_ids:
                adapter.release_holds(created_ids)
            return {
                "ok": False,
                "hold_ids": [],
                "released_ids": released_ids,
                "available_qty": result["available_qty"],
                "is_paused": result.get("is_paused", False),
                "error_code": result.get("error_code", "hold_failed"),
                "alternatives": alternatives.find(
                    bundle_sku, qty=bundle_qty, channel=channel_ref,
                ),
            }
        created_ids.extend(result["hold_ids"])
        released_ids.extend(result["released_ids"])

    return {
        "ok": True,
        "hold_ids": created_ids,
        "released_ids": released_ids,
        "available_qty": Decimal("0"),
        "is_paused": False,
        "error_code": None,
        "alternatives": [],
    }


def _reserve_bundle_components(
    bundle_sku: str,
    bundle_qty: Decimal,
    components: list[dict],
    *,
    session_key: str,
    ttl_minutes: int,
    channel_ref: str | None,
    available_qty: Decimal,
    adapter,
) -> dict:
    """Create one hold per bundle component.

    On any failure, releases all previously created holds (atomic rollback)
    and returns ok=False.
    """
    created_hold_ids: list[str] = []

    for comp in components:
        comp_sku = comp["sku"]
        comp_qty = Decimal(str(comp["qty"]))

        result = adapter.create_hold(
            sku=comp_sku,
            qty=comp_qty,
            ttl_minutes=ttl_minutes,
            reference=session_key,
        )

        if not result.get("success"):
            logger.info(
                "availability.reserve: bundle hold failed sku=%s comp=%s qty=%s code=%s",
                bundle_sku, comp_sku, comp_qty, result.get("error_code"),
            )
            # Rollback: release holds already created for previous components.
            if created_hold_ids:
                adapter.release_holds(created_hold_ids)
            return {
                "ok": False,
                "hold_id": None,
                "hold_ids": [],
                "available_qty": available_qty,
                "is_paused": False,
                "error_code": result.get("error_code", "hold_failed"),
                "is_bundle": True,
                "alternatives": alternatives.find(bundle_sku, qty=bundle_qty, channel=channel_ref),
            }

        created_hold_ids.append(result["hold_id"])

    return {
        "ok": True,
        "hold_id": None,          # use hold_ids for bundles
        "hold_ids": created_hold_ids,
        "available_qty": available_qty,
        "is_paused": False,
        "error_code": None,
        "is_bundle": True,
        "alternatives": [],
    }
