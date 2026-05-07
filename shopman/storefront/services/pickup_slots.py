"""Pickup slot service — maps products to time slots based on production history.

Each product has a "typical ready time" derived from the median finish time
of its recent WorkOrders.  When a customer builds a cart with multiple items,
the earliest available pickup slot is the one that covers both the latest
typical_ready_time among all items and the current wall clock.

Configuration lives in Shop.defaults["pickup_slots"] (admin-editable):

    [
        {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
        {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
        {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
    ]
"""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from statistics import median

logger = logging.getLogger(__name__)


def _wall_clock() -> time:
    try:
        from django.utils import timezone

        return timezone.localtime().time().replace(second=0, microsecond=0)
    except Exception:
        logger.debug("pickup_slots: could not read Django local time", exc_info=True)
        return datetime.now().time().replace(second=0, microsecond=0)


# ── Defaults ─────────────────────────────────────────────────────────

DEFAULT_SLOTS = [
    {"ref": "slot-09", "label": "A partir das 09h", "starts_at": "09:00"},
    {"ref": "slot-12", "label": "A partir das 12h", "starts_at": "12:00"},
    {"ref": "slot-15", "label": "A partir das 15h", "starts_at": "15:00"},
]

DEFAULT_ROUNDING_MINUTES = 30
DEFAULT_HISTORY_DAYS = 30
DEFAULT_FALLBACK_SLOT = "slot-09"


def _parse_time(t: str) -> time:
    """Parse 'HH:MM' into time object."""
    parts = t.split(":")
    return time(int(parts[0]), int(parts[1]))


def _sorted_slots(slots: list[dict]) -> list[dict]:
    return sorted(slots, key=lambda s: _parse_time(s["starts_at"]))


def _slot_at_or_after(slots: list[dict], threshold: time) -> dict:
    """Return first slot that starts at/after ``threshold``, or the last slot."""
    ordered = _sorted_slots(slots)
    chosen = ordered[-1]
    for slot in ordered:
        if _parse_time(slot["starts_at"]) >= threshold:
            chosen = slot
            break
    return chosen


def _current_or_next_slot(slots: list[dict], clock: time) -> dict:
    """Return the currently active "a partir" slot, or the first future slot."""
    ordered = _sorted_slots(slots)
    current = ordered[0]
    for slot in ordered:
        if _parse_time(slot["starts_at"]) <= clock:
            current = slot
        else:
            break
    return current


def _later_slot(slots: list[dict], *candidates: dict) -> dict:
    ordered = _sorted_slots(slots)
    rank = {slot["ref"]: i for i, slot in enumerate(ordered)}
    return max(candidates, key=lambda slot: rank.get(slot["ref"], -1))


def is_slot_available_for_today(slots: list[dict], slot_ref: str, *, now: time | None = None) -> bool:
    """Return whether a pickup slot is still selectable today.

    Slot labels are "A partir das HHh": a slot remains available after its
    start until a later configured slot starts. The last slot therefore stays
    selectable for the rest of the day.
    """
    slot = _find_slot_by_ref(slots, slot_ref)
    if slot is None:
        return False
    clock = now or _wall_clock()
    current = _current_or_next_slot(slots, clock)
    slot_start = _parse_time(slot["starts_at"])
    return slot_start > clock or slot["ref"] == current["ref"]


# ── Public API ───────────────────────────────────────────────────────


def get_slots() -> list[dict]:
    """Return configured pickup slots from Shop.defaults, or defaults."""
    try:
        from shopman.shop.models import Shop
        shop = Shop.load()
        if shop:
            slots = (shop.defaults or {}).get("pickup_slots")
            if slots:
                return slots
    except Exception:
        logger.debug("pickup_slots: could not load configured slots", exc_info=True)
    return list(DEFAULT_SLOTS)


def get_slot_config() -> dict:
    """Return pickup slot configuration from Shop.defaults."""
    try:
        from shopman.shop.models import Shop
        shop = Shop.load()
        if shop:
            return (shop.defaults or {}).get("pickup_slot_config", {})
    except Exception:
        logger.debug("pickup_slots: could not load slot config", exc_info=True)
    return {}


def get_typical_ready_times(
    skus: list[str],
    *,
    history_days: int | None = None,
    rounding_minutes: int | None = None,
) -> dict[str, time]:
    """Compute typical ready time per SKU from WorkOrder finish history.

    Looks at WorkOrders completed in the last ``history_days`` days,
    takes the median finish time-of-day, and rounds UP to the nearest
    ``rounding_minutes`` boundary.

    Returns ``{sku: time}`` for SKUs that have production history.
    SKUs without data are omitted (caller uses fallback slot).
    """
    config = get_slot_config()
    if history_days is None:
        history_days = config.get("history_days", DEFAULT_HISTORY_DAYS)
    if rounding_minutes is None:
        rounding_minutes = config.get("rounding_minutes", DEFAULT_ROUNDING_MINUTES)

    try:
        from shopman.shop.adapters import get_adapter
        production = get_adapter("production")
    except ImportError:
        return {}

    cutoff = date.today() - timedelta(days=history_days)

    # Single query: all finished WorkOrders for these SKUs in the window
    wos = production.get_finished_work_orders(skus, cutoff)

    # Group finish times by SKU
    times_by_sku: dict[str, list[float]] = {}
    for sku, finished_at in wos:
        # Convert to local time, extract time-of-day as minutes since midnight
        if hasattr(finished_at, "astimezone"):
            from django.utils import timezone as tz
            local_dt = finished_at.astimezone(tz.get_current_timezone())
        else:
            local_dt = finished_at
        minutes = local_dt.hour * 60 + local_dt.minute
        times_by_sku.setdefault(sku, []).append(minutes)

    result: dict[str, time] = {}
    for sku, minutes_list in times_by_sku.items():
        if not minutes_list:
            continue
        median_minutes = median(minutes_list)
        rounded = _round_up_minutes(median_minutes, rounding_minutes)
        h = min(int(rounded // 60), 23)
        m = int(rounded % 60)
        result[sku] = time(h, m)

    return result


def _round_up_minutes(minutes: float, granularity: int) -> int:
    """Round minutes UP to the nearest granularity boundary.

    >>> _round_up_minutes(330, 30)  # 5:30 → 5:30 (exact)
    330
    >>> _round_up_minutes(331, 30)  # 5:31 → 6:00
    360
    >>> _round_up_minutes(690, 30)  # 11:30 → 11:30 (exact)
    690
    """
    import math
    return int(math.ceil(minutes / granularity) * granularity)


def get_earliest_slot_for_skus(skus: list[str]) -> dict:
    """Determine the earliest pickup slot that covers all given SKUs.

    Returns::

        {
            "slot": {"ref": "slot-12", "label": "...", "starts_at": "12:00"},
            "slot_ref": "slot-12",
            "ready_times": {"PAO-FRANCES": "05:30", "BOLO-CHOCOLATE": "11:30"},
            "bottleneck_sku": "BOLO-CHOCOLATE",
        }

    If no production data exists for any SKU, returns the fallback slot.
    """
    slots = get_slots()
    if not slots:
        return {"slot": None, "slot_ref": None, "ready_times": {}, "bottleneck_sku": None}

    config = get_slot_config()
    fallback_ref = config.get("fallback_slot", DEFAULT_FALLBACK_SLOT)

    ready_times = get_typical_ready_times(skus)

    if not ready_times:
        # No production data — use the configured fallback, but never select
        # a slot whose "a partir" window has already been superseded today.
        fallback = _find_slot_by_ref(slots, fallback_ref) or _sorted_slots(slots)[0]
        chosen = _later_slot(slots, fallback, _current_or_next_slot(slots, _wall_clock()))
        return {
            "slot": chosen,
            "slot_ref": chosen["ref"],
            "ready_times": {},
            "bottleneck_sku": None,
        }

    # Find the latest ready time among all cart items
    latest_time = time(0, 0)
    bottleneck_sku = None
    for sku, t in ready_times.items():
        if t > latest_time:
            latest_time = t
            bottleneck_sku = sku

    readiness_slot = _slot_at_or_after(slots, latest_time)
    clock_slot = _current_or_next_slot(slots, _wall_clock())
    chosen = _later_slot(slots, readiness_slot, clock_slot)

    return {
        "slot": chosen,
        "slot_ref": chosen["ref"],
        "ready_times": {sku: t.strftime("%H:%M") for sku, t in ready_times.items()},
        "bottleneck_sku": bottleneck_sku,
    }


def annotate_slots_for_checkout(cart_skus: list[str]) -> dict:
    """Build full context for checkout template.

    Returns::

        {
            "pickup_slots": [...],        # all configured slots
            "earliest_slot_ref": "...",   # earliest available for this cart
            "bottleneck_sku": "...",       # the SKU that pushes the slot
            "ready_times": {...},          # {sku: "HH:MM"}
        }
    """
    slots = get_slots()
    result = get_earliest_slot_for_skus(cart_skus)

    return {
        "pickup_slots": slots,
        "earliest_slot_ref": result["slot_ref"],
        "bottleneck_sku": result["bottleneck_sku"],
        "ready_times": result["ready_times"],
    }


def _find_slot_by_ref(slots: list[dict], ref: str) -> dict | None:
    for s in slots:
        if s["ref"] == ref:
            return s
    return None
