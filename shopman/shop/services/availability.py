"""
Availability service — canonical sync API for stock checks and reservations.

This is the FIRST-CLASS service for "can the customer order this?" across all
channels (storefront cart, POS, totem, marketplace inbound). It wraps:

- Stockman.availability (read) — orderable/reserved/breakdown by SKU and channel
- adapters.stock.create_hold (write) — actual hold creation in Stockman
- services.substitutes.find (suggest) — fallback substitutes on shortage

Three verbs:

    check(sku, qty, *, channel_ref) -> dict
        Read-only. Returns whether `qty` of `sku` can be ordered now.

    reserve(sku, qty, *, session_key, channel_ref, ttl_minutes=30) -> dict
        Write. Checks first; if available, creates a hold tagged with session_key
        as `reference` so the order's CommitService can adopt it. On shortage,
        populates `substitutes` with suggested SKUs.

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
from datetime import date
from decimal import Decimal

from shopman.shop.adapters import get_adapter
from shopman.shop.models import Channel

from . import substitutes

logger = logging.getLogger(__name__)


def bump_session_hold_expiry(session_key: str, *, ttl_minutes: int = 30) -> int:
    """Extend the TTL of every active hold tagged with ``session_key``.

    Called from the cart's write paths (add/update/set_qty) so the session's
    holds stay alive as long as the shopper is active. Orphaned holds from
    abandoned sessions still die naturally at their TTL — this just keeps
    the "active shopper" case alive.

    Indefinite holds (``expires_at IS NULL`` — planned holds) are untouched:
    their TTL only starts after materialization (AVAILABILITY-PLAN §8).

    Returns the number of holds whose ``expires_at`` was bumped.
    """
    if not session_key:
        return 0
    try:
        from datetime import timedelta

        from django.utils import timezone
        from shopman.stockman import Hold, HoldStatus
    except Exception:
        return 0

    new_expiry = timezone.now() + timedelta(minutes=ttl_minutes)
    return (
        Hold.objects.filter(
            metadata__reference=session_key,
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
            expires_at__isnull=False,
            expires_at__lt=new_expiry,
        )
        .update(expires_at=new_expiry)
    )


def classify_planned_hold_for_session_sku(
    session_key: str, sku: str,
) -> dict:
    """Classify the planned-hold state of the session's holds for a SKU.

    Planned holds (AVAILABILITY-PLAN §8) are the "reservation without a
    running TTL" state that holds on planned production / demand-only
    quants land on. The marker ``metadata.planned`` is stamped at hold
    creation by the stock adapter and survives the transition to the
    ready state — post-materialization the flag remains while
    ``expires_at`` goes from ``None`` (awaiting confirmation) to a
    concrete deadline set by ``StockPlanning.realize()``.

    Returns:
        {
            "is_awaiting_confirmation": bool,   # any planned hold still pre-materialization
            "is_ready_for_confirmation": bool,  # all planned holds have materialized
            "deadline": datetime | None,        # earliest materialized deadline (min expires_at)
        }

    With multiple holds (split reservation, partial materialization) the
    rule is binary:
    - ``is_awaiting_confirmation`` = OR of every hold's pre-materialization state.
    - ``is_ready_for_confirmation`` = AND of every hold's ready state (ALL
      must have materialized before the badge flips to "Tudo pronto!").
    """
    empty = {
        "is_awaiting_confirmation": False,
        "is_ready_for_confirmation": False,
        "deadline": None,
    }
    if not session_key or not sku:
        return empty
    try:
        from django.db.models import Q
        from django.utils import timezone
        from shopman.stockman import Hold, HoldStatus
    except Exception:
        return empty

    holds = list(
        Hold.objects.filter(
            metadata__reference=session_key,
            metadata__planned=True,
            sku=sku,
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
    )
    if not holds:
        return empty

    any_awaiting = any(h.expires_at is None for h in holds)
    all_ready = all(h.expires_at is not None for h in holds)
    deadline = None
    if all_ready:
        deadline = min(h.expires_at for h in holds)

    return {
        "is_awaiting_confirmation": any_awaiting,
        "is_ready_for_confirmation": all_ready,
        "deadline": deadline,
    }


def own_holds_by_sku(session_key: str, skus: list[str]) -> dict[str, Decimal]:
    """Sum this session's active hold quantity per SKU (single batch query).

    Canonical helper consumed by the storefront read paths (cart, PDP) that
    need to distinguish between "this SKU is unavailable to the public" and
    "this session already holds all of it". Without it, a customer who
    reserved the last N units sees "indisponível" on every surface — the
    hold is double-counted against them.

    Empty ``session_key`` or ``skus`` → ``{}`` (anonymous browsing, no cart).
    Returns ``{sku: held_qty}`` only for SKUs with active holds.
    """
    if not session_key or not skus:
        return {}
    try:
        from django.db.models import Q, Sum
        from django.utils import timezone
        from shopman.stockman import Hold, HoldStatus
    except Exception:
        return {}

    rows = (
        Hold.objects.filter(
            metadata__reference=session_key,
            sku__in=skus,
            status__in=[HoldStatus.PENDING, HoldStatus.CONFIRMED],
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gte=timezone.now()))
        .values("sku")
        .annotate(total=Sum("quantity"))
    )
    return {row["sku"]: row["total"] or Decimal("0") for row in rows}


def decide(
    sku: str,
    qty: Decimal,
    *,
    channel_ref: str | None = None,
    target_date: date | None = None,
) -> dict:
    """Return a canonical promise decision for one SKU in context."""
    qty_d = Decimal(str(qty))

    components = _expand_if_bundle(sku, qty_d)
    if components is not None:
        bundle_result = _check_bundle(
            sku,
            qty_d,
            components,
            channel_ref=channel_ref,
            target_date=target_date,
        )
        return {
            "approved": bundle_result["ok"],
            "sku": sku,
            "requested_qty": qty_d,
            "available_qty": bundle_result["available_qty"],
            "reason_code": bundle_result.get("error_code"),
            "is_paused": bundle_result.get("is_paused", False),
            "is_planned": bundle_result.get("is_planned", False),
            "target_date": target_date,
            "failed_sku": bundle_result.get("failed_sku"),
            "source": "availability.bundle_decision",
        }

    listing_item = _sku_in_channel_listing(sku, channel_ref)
    if listing_item is False:
        return {
            "approved": False,
            "sku": sku,
            "requested_qty": qty_d,
            "available_qty": Decimal("0"),
            "reason_code": "not_in_listing",
            "is_paused": False,
            "is_planned": False,
            "target_date": target_date,
            "failed_sku": None,
            "source": "availability.listing_gate",
        }
    if isinstance(listing_item, dict) and not listing_item.get("is_sellable", True):
        return {
            "approved": False,
            "sku": sku,
            "requested_qty": qty_d,
            "available_qty": Decimal("0"),
            "reason_code": "paused",
            "is_paused": True,
            "is_planned": False,
            "target_date": target_date,
            "failed_sku": None,
            "source": "availability.listing_gate",
        }
    # ``ListingItem.min_qty`` is kept in the model but not enforced at the
    # gate (AVAILABILITY-PLAN §10 — ``below_min_qty`` is YAGNI today).
    # Future B2B/MOQ scenarios should resurrect this with proper UX.

    adapter = get_adapter("stock")
    scope = adapter.get_channel_scope(channel_ref)
    info = adapter.get_availability(
        sku,
        target_date=target_date,
        safety_margin=scope["safety_margin"],
        allowed_positions=scope["allowed_positions"],
        excluded_positions=scope.get("excluded_positions"),
    )
    if not info.get("is_paused", False) and not info.get("is_tracked", bool(info.get("positions"))):
        return {
            "approved": True,
            "sku": sku,
            "requested_qty": qty_d,
            "available_qty": Decimal("999999"),
            "reason_code": None,
            "is_paused": False,
            "is_planned": False,
            "target_date": target_date,
            "failed_sku": None,
            "source": "stock.untracked",
            "untracked": True,
        }

    decision = adapter.get_promise_decision(
        sku,
        qty_d,
        target_date=target_date,
        safety_margin=scope["safety_margin"],
        allowed_positions=scope["allowed_positions"],
        excluded_positions=scope.get("excluded_positions"),
    )
    approved = decision.approved if isinstance(getattr(decision, "approved", None), bool) else qty_d <= info["total_promisable"]
    reason_code = getattr(decision, "reason_code", None)
    if not isinstance(reason_code, str | type(None)):
        reason_code = None if approved else ("paused" if info.get("is_paused", False) else "insufficient_stock")
    return {
        "approved": approved,
        "sku": getattr(decision, "sku", sku),
        "requested_qty": getattr(decision, "requested_qty", qty_d),
        "available_qty": getattr(decision, "available_qty", info["total_promisable"]),
        "reason_code": reason_code,
        "is_paused": getattr(decision, "is_paused", info.get("is_paused", False)),
        "is_planned": getattr(decision, "is_planned", info.get("is_planned", False)),
        "target_date": getattr(decision, "target_date", target_date),
        "failed_sku": None,
        "source": "stock.promise_decision",
    }


def check(
    sku: str,
    qty: Decimal,
    *,
    channel_ref: str | None = None,
    target_date: date | None = None,
) -> dict:
    """
    Read-only availability check for a single SKU/qty in a channel scope.

    If the SKU is a bundle, expands it via CatalogService.expand() and runs
    check() recursively for each component. Returns ok=False at the first
    failing component (with failed_sku identifying it) or ok=True with
    available_qty = min constructable bundles if all components pass.

    Validations applied for simple SKUs (in order):
      1. Channel listing gate — if `channel_ref` is provided and the
         channel has a `listing_ref`, the SKU must belong structurally to that
         listing. If the listing item exists but is strategically not sellable,
         the result is ok=False with error_code="paused". If no listing item
         exists at all, ok=False with error_code="not_in_listing".
      2. Stockman availability — Offerman global pause (`is_paused`),
         per-channel safety_margin and allowed_positions, plus physical
         stock breakdown.

    Returns:
        {
            "ok": bool,                 # passes listing check AND stock check
            "available_qty": Decimal,   # total_promisable for this channel
            "is_paused": bool,          # product paused/unpublished
            "is_planned": bool,         # only future quants exist
            "breakdown": {ready, in_production, d1},
            "error_code": str | None,   # set when ok=False
            "is_bundle": bool,          # True when SKU is a bundle
            "failed_sku": str | None,   # component that caused failure (bundles only)
        }
    """
    decision = decide(
        sku,
        qty,
        channel_ref=channel_ref,
        target_date=target_date,
    )
    return {
        "ok": decision["approved"],
        "available_qty": decision["available_qty"],
        "is_paused": decision["is_paused"],
        "is_planned": decision["is_planned"],
        "breakdown": {},
        "error_code": decision["reason_code"],
        "is_bundle": decision["source"] == "availability.bundle_decision",
        "failed_sku": decision.get("failed_sku"),
        "target_date": target_date,
        "untracked": decision.get("untracked", False),
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
    target_date: date | None,
) -> dict:
    """Check availability of all bundle components recursively.

    Returns ok=False at the first failing component, or ok=True with
    available_qty = number of full bundles constructable from components.
    """
    min_constructable: Decimal | None = None

    for comp in components:
        comp_sku = comp["sku"]
        comp_qty = Decimal(str(comp["qty"]))

        result = check(comp_sku, comp_qty, channel_ref=channel_ref, target_date=target_date)

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
                "target_date": target_date,
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
        "target_date": target_date,
    }


def _sku_in_channel_listing(sku: str, channel_ref: str | None) -> dict | bool:
    """Return listing item dict when the SKU belongs to the channel's listing.

    Returns True when the check is skipped (no channel_ref or no listing_ref),
    False when the SKU fails the listing gate.

    Callers treat True as "gate skipped", a dict as "gate passed with item data"
    (used for min_qty and sellability checks), and False as "gate failed".

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
    target_date: date | None = None,
    ttl_minutes: int = 30,
) -> dict:
    """
    Inline check + hold creation for the storefront/POS/marketplace flows.

    On success: creates a Stockman hold tagged with `reference=session_key` so
    the eventual CommitService can adopt the holds when the order is created.

    On shortage or pause: returns ok=False with `substitutes` populated via
    services.substitutes.find().

    Returns:
        {
            "ok": bool,
            "hold_id": str | None,
            "available_qty": Decimal,
            "is_paused": bool,
            "error_code": str | None,    # only when ok=False
            "substitutes": list[dict],  # only when ok=False
        }
    """
    qty_d = Decimal(str(qty))
    status = check(sku, qty_d, channel_ref=channel_ref, target_date=target_date)

    # SKUs that are not tracked by Stockman: skip the hold (the order will
    # commit without stock reservation, same as the legacy noop path).
    if status.get("untracked"):
        return {
            "ok": True,
            "hold_id": None,
            "available_qty": status["available_qty"],
            "is_paused": False,
            "error_code": None,
            "substitutes": [],
        }

    if not status["ok"]:
        return {
            "ok": False,
            "hold_id": None,
            "available_qty": status["available_qty"],
            "is_paused": status["is_paused"],
            "is_planned": status.get("is_planned", False),
            "error_code": status.get("error_code") or (
                "paused" if status["is_paused"] else "insufficient_stock"
            ),
            "substitutes": substitutes.find(sku, qty=qty_d, channel=channel_ref),
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
                target_date=target_date,
                available_qty=status["available_qty"],
                adapter=adapter,
            )

    result = adapter.create_hold(
        sku=sku,
        qty=qty_d,
        ttl_minutes=ttl_minutes,
        reference=session_key,
        target_date=target_date,
        channel_ref=channel_ref,
    )

    if not result.get("success"):
        # Stockman's Hold model pins each hold to a single Quant. When the
        # requested qty fits in the channel's total_promisable but not in any
        # single quant (stock fragmented across positions/batches), the hold
        # fails with INSUFFICIENT_AVAILABLE even though check() said ok.
        #
        # Split the request into multiple partial holds, one per quant, so
        # the caller receives the qty it legitimately has access to. All
        # partial holds share the same session_key reference so CommitService
        # adopts them together.
        if result.get("error_code") == "INSUFFICIENT_AVAILABLE":
            partial = _reserve_across_quants(
                sku=sku, qty=qty_d,
                ttl_minutes=ttl_minutes,
                session_key=session_key,
                channel_ref=channel_ref,
                target_date=target_date,
                adapter=adapter,
            )
            if partial["ok"]:
                return partial
            # Fall through to 422 with partial["available_qty"] reflecting what
            # we could actually hold (may be less than status.available_qty).
            return {
                "ok": False,
                "hold_id": None,
                "available_qty": partial["available_qty"],
                "is_paused": False,
                "is_planned": False,
                "error_code": "insufficient_stock",
                "substitutes": substitutes.find(sku, qty=qty_d, channel=channel_ref),
            }

        logger.info(
            "availability.reserve: hold failed sku=%s qty=%s code=%s",
            sku, qty_d, result.get("error_code"),
        )
        return {
            "ok": False,
            "hold_id": None,
            "available_qty": status["available_qty"],
            "is_paused": False,
            "is_planned": False,
            "error_code": result.get("error_code", "hold_failed"),
            "substitutes": substitutes.find(sku, qty=qty_d, channel=channel_ref),
        }

    return {
        "ok": True,
        "hold_id": result["hold_id"],
        "available_qty": status["available_qty"],
        "is_paused": False,
        "error_code": None,
        "substitutes": [],
    }


def _reserve_across_quants(
    *,
    sku: str,
    qty: Decimal,
    ttl_minutes: int,
    session_key: str,
    channel_ref: str | None,
    target_date: date | None,
    adapter,
) -> dict:
    """Split a reservation across multiple quants/batches when no single quant
    fits the full qty. All partial holds share ``reference=session_key`` so
    Commit adopts them together.

    Returns the same shape as ``reserve()``; on partial success (stock covered
    exactly), ``hold_id`` carries the first hold id for compatibility and
    ``ok=True``. When the combined quant capacity is still short, returns
    ``ok=False`` with ``available_qty`` reflecting what actually fit.
    """
    remaining = Decimal(qty)
    reserved = Decimal("0")
    first_hold_id: str | None = None
    created_hold_ids: list[str] = []
    attempts = 0
    # Hard cap to avoid infinite loops if adapter misbehaves.
    while remaining > 0 and attempts < 32:
        attempts += 1
        # Binary search downward: try remaining, then half, etc., until the
        # adapter accepts a single-quant hold.
        current_try = remaining
        accepted = False
        while current_try > 0:
            r = adapter.create_hold(
                sku=sku,
                qty=current_try,
                ttl_minutes=ttl_minutes,
                reference=session_key,
                target_date=target_date,
                channel_ref=channel_ref,
            )
            if r.get("success"):
                if first_hold_id is None:
                    first_hold_id = r["hold_id"]
                created_hold_ids.append(r["hold_id"])
                reserved += current_try
                remaining -= current_try
                accepted = True
                break
            if r.get("error_code") != "INSUFFICIENT_AVAILABLE":
                break
            # Halve and retry. Decimal halving is exact enough for integer units.
            current_try = (current_try // 2)
        if not accepted:
            break

    if remaining > 0:
        # Roll back whatever we reserved so the cart does not end up with a
        # partial reservation that the customer did not consent to.
        if created_hold_ids:
            try:
                adapter.release_holds(created_hold_ids)
            except Exception:
                logger.warning(
                    "availability.reserve: failed to release partial holds %s",
                    created_hold_ids,
                )
        logger.info(
            "availability.reserve: split holds insufficient sku=%s asked=%s reserved=%s",
            sku, qty, reserved,
        )
        return {"ok": False, "available_qty": int(reserved)}

    logger.info(
        "availability.reserve: split across %d holds sku=%s qty=%s",
        len(created_hold_ids), sku, qty,
    )
    return {
        "ok": True,
        "hold_id": first_hold_id,
        "available_qty": int(qty),
        "is_paused": False,
        "error_code": None,
        "substitutes": [],
    }


def reconcile(
    sku: str,
    new_qty: Decimal,
    *,
    session_key: str,
    channel_ref: str | None = None,
    target_date: date | None = None,
    ttl_minutes: int = 30,
) -> dict:
    """
    Bring the total reserved qty for `(session_key, sku)` to exactly `new_qty`.

    Used by the cart's stepper and remove flows: while `reserve()` assumes a
    brand-new additive reservation, `reconcile()` computes the delta against
    the session's existing holds for the SKU and adjusts accordingly.

    Grow (`new_qty > current`):
        Runs `check()` first; creates a hold for `(new_qty - current)`. On
        shortage or hold failure, returns `ok=False` with substitutes and
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
            "substitutes": list[dict],
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
                target_date=target_date,
                ttl_minutes=ttl_minutes,
            )
    else:
        # new_qty == 0 on a potential bundle: release the component holds this
        # session reserved for the bundle, surgically (FIFO, bounded by the
        # expected per-component qty). Previously this was deferred to
        # commit-time which left orphan holds when the shopper abandoned the
        # cart (AVAILABILITY-PLAN Gap D).
        probe = _expand_if_bundle(sku, Decimal("1"))
        if probe is not None:
            per_unit_components = _expand_if_bundle(sku, Decimal("1")) or []
            released_ids = _release_bundle_component_holds(
                session_key=session_key,
                components=per_unit_components,
            )
            logger.info(
                "availability.reconcile: bundle %s released %d component holds",
                sku, len(released_ids),
            )
            return {
                "ok": True,
                "hold_ids": [],
                "released_ids": released_ids,
                "available_qty": Decimal("0"),
                "is_paused": False,
                "error_code": None,
                "substitutes": [],
            }

    return _reconcile_simple(
        sku, new_qty_d,
        session_key=session_key,
        channel_ref=channel_ref,
        target_date=target_date,
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
    target_date: date | None,
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
            "substitutes": [],
        }

    adapter = get_adapter("stock")

    # ── Grow ──
    if new_qty > current_total:
        delta = new_qty - current_total
        status = check(sku, delta, channel_ref=channel_ref, target_date=target_date)

        if status.get("untracked"):
            # SKU outside Stockman scope — no hold needed, treat as ok.
            return {
                "ok": True,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": status["available_qty"],
                "is_paused": False,
                "error_code": None,
                "substitutes": [],
            }

        if not status["ok"]:
            return {
                "ok": False,
                "hold_ids": [],
                "released_ids": [],
                "available_qty": status["available_qty"],
                "is_paused": status.get("is_paused", False),
                "error_code": status.get("error_code") or "insufficient_stock",
                "substitutes": substitutes.find(sku, qty=delta, channel=channel_ref),
            }

        result = adapter.create_hold(
            sku=sku,
            qty=delta,
            ttl_minutes=ttl_minutes,
            reference=session_key,
            target_date=target_date,
            channel_ref=channel_ref,
        )
        if not result.get("success"):
            # Fragmented stock: fall back to multi-quant split reservation.
            if result.get("error_code") == "INSUFFICIENT_AVAILABLE":
                split = _reserve_across_quants(
                    sku=sku, qty=delta,
                    ttl_minutes=ttl_minutes,
                    session_key=session_key,
                    channel_ref=channel_ref,
                    target_date=target_date,
                    adapter=adapter,
                )
                if split["ok"]:
                    return {
                        "ok": True,
                        "hold_ids": [split["hold_id"]],
                        "released_ids": [],
                        "available_qty": status["available_qty"],
                        "is_paused": False,
                        "error_code": None,
                        "substitutes": [],
                    }
                return {
                    "ok": False,
                    "hold_ids": [],
                    "released_ids": [],
                    "available_qty": split["available_qty"],
                    "is_paused": False,
                    "error_code": "insufficient_stock",
                    "substitutes": substitutes.find(sku, qty=delta, channel=channel_ref),
                }
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
                "substitutes": substitutes.find(sku, qty=delta, channel=channel_ref),
            }
        return {
            "ok": True,
            "hold_ids": [result["hold_id"]],
            "released_ids": [],
            "available_qty": status["available_qty"],
            "is_paused": False,
            "error_code": None,
            "substitutes": [],
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
            target_date=target_date,
            channel_ref=channel_ref,
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
        "substitutes": [],
    }


def _release_bundle_component_holds(
    *,
    session_key: str,
    components: list[dict],
) -> list[str]:
    """Release this session's holds for each bundle component, up to the
    per-unit component qty declared in ``components``.

    Surgical vs. "release every hold of this SKU for this session" — we only
    free what THIS bundle removal should free, by walking the session's
    existing holds FIFO and stopping when the component's expected qty is
    covered. If the session has concurrent bundles or simple lines sharing
    the same component SKU, the remainder stays held; later reconcile/commit
    flows can re-balance.

    Returns the list of released hold_ids.
    """
    adapter = get_adapter("stock")
    released: list[str] = []
    for comp in components:
        comp_sku = comp.get("sku")
        comp_qty = Decimal(str(comp.get("qty") or 0))
        if not comp_sku or comp_qty <= 0:
            continue
        try:
            session_holds = adapter.find_holds_by_reference(session_key, sku=comp_sku)
        except Exception as e:
            logger.warning(
                "release_bundle_components: find_holds failed sku=%s: %s",
                comp_sku, e, exc_info=True,
            )
            continue
        to_free: list[str] = []
        remaining = comp_qty
        for hold_id, _sku, held_qty in session_holds:
            if remaining <= 0:
                break
            to_free.append(hold_id)
            remaining -= held_qty
        if to_free:
            try:
                adapter.release_holds(to_free)
                released.extend(to_free)
            except Exception as e:
                logger.warning(
                    "release_bundle_components: release_holds failed ids=%s: %s",
                    to_free, e, exc_info=True,
                )
    return released


def _reconcile_bundle_components(
    bundle_sku: str,
    bundle_qty: Decimal,
    components: list[dict],
    *,
    session_key: str,
    channel_ref: str | None,
    target_date: date | None,
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
            target_date=target_date,
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
                "substitutes": substitutes.find(
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
        "substitutes": [],
    }


def _reserve_bundle_components(
    bundle_sku: str,
    bundle_qty: Decimal,
    components: list[dict],
    *,
    session_key: str,
    ttl_minutes: int,
    channel_ref: str | None,
    target_date: date | None,
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
            target_date=target_date,
            channel_ref=channel_ref,
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
                "substitutes": substitutes.find(bundle_sku, qty=bundle_qty, channel=channel_ref),
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
        "substitutes": [],
    }
