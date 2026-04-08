"""
Availability service — canonical sync API for stock checks and reservations.

This is the FIRST-CLASS service for "can the customer order this?" across all
channels (storefront cart, POS, totem, marketplace inbound). It wraps:

- Stockman.availability (read) — orderable/reserved/breakdown by SKU and channel
- adapters.stock.create_hold (write) — actual hold creation in Stockman
- services.alternatives.find (suggest) — fallback alternatives on shortage

Two verbs:

    check(sku, qty, *, channel_ref) -> dict
        Read-only. Returns whether `qty` of `sku` can be ordered now.

    reserve(sku, qty, *, session_key, channel_ref, ttl_minutes=30) -> dict
        Write. Checks first; if available, creates a hold tagged with session_key
        as `reference` so the order's CommitService can adopt it. On shortage,
        populates `alternatives` with suggested SKUs.

Both return plain dicts so callers (cart UX, marketplace flow, API) can react
without coupling to Stockman internals.
"""

from __future__ import annotations

import logging
from decimal import Decimal

from shopman.adapters import get_adapter
from shopman.offerman.service import CatalogService

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
        min_qty = getattr(listing_item, "min_qty", None)
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
    try:
        from shopman.stockman.services.availability import (
            availability_for_sku,
            availability_scope_for_channel,
        )
    except ImportError:
        return {
            "ok": False,
            "available_qty": Decimal("0"),
            "is_paused": False,
            "is_planned": False,
            "breakdown": {"ready": Decimal("0"), "in_production": Decimal("0"), "d1": Decimal("0")},
            "error_code": "stocking_not_installed",
            "is_bundle": False,
            "failed_sku": None,
        }

    scope = availability_scope_for_channel(channel_ref)
    info = availability_for_sku(
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

    Returns None (not a bundle) when CatalogService.expand raises any error,
    including NOT_A_BUNDLE and SKU_NOT_FOUND — callers handle missing SKU
    via the Stockman gate.
    """
    try:
        from shopman.offerman.exceptions import CatalogError
        components = CatalogService.expand(sku, qty)
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


def _sku_in_channel_listing(sku: str, channel_ref: str | None) -> "ListingItem | bool":
    """Return ListingItem when the SKU is published+available in the channel's listing.

    Returns True when the check is skipped (no channel_ref or no listing_ref),
    False when the SKU fails the listing gate.

    Callers treat True as "gate skipped", a ListingItem object as "gate passed
    with item data" (used for min_qty checks), and False as "gate failed".

    If the channel has no `listing_ref` configured, the check is skipped
    (returns True) — this preserves backward compatibility for channels that
    don't constrain their catalog (e.g. internal POS).
    """
    if not channel_ref:
        return True

    try:
        from shopman.offerman.models import ListingItem
        from shopman.omniman.models import Channel
    except ImportError:
        return True

    try:
        channel = Channel.objects.get(ref=channel_ref)
    except Channel.DoesNotExist:
        return True

    listing_ref = getattr(channel, "listing_ref", None)
    if not listing_ref:
        return True

    try:
        return ListingItem.objects.get(
            listing__ref=listing_ref,
            listing__is_active=True,
            product__sku=sku,
            is_published=True,
            is_available=True,
        )
    except ListingItem.DoesNotExist:
        return False
    except ListingItem.MultipleObjectsReturned:
        # Multiple active listing items — gate passes, use first
        return ListingItem.objects.filter(
            listing__ref=listing_ref,
            listing__is_active=True,
            product__sku=sku,
            is_published=True,
            is_available=True,
        ).first() or False


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
