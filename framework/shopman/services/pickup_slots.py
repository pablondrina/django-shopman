"""Pickup slot service — maps products to time slots based on production history.

Each product has a "typical ready time" derived from the median finish time
of its recent WorkOrders.  When a customer builds a cart with multiple items,
the earliest available pickup slot is the one that starts AFTER the latest
typical_ready_time among all items.

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


# ── Public API ───────────────────────────────────────────────────────


def get_slots() -> list[dict]:
    """Return configured pickup slots from Shop.defaults, or defaults."""
    try:
        from shopman.models import Shop
        shop = Shop.load()
        if shop:
            slots = (shop.defaults or {}).get("pickup_slots")
            if slots:
                return slots
    except Exception:
        pass
    return list(DEFAULT_SLOTS)


def get_slot_config() -> dict:
    """Return pickup slot configuration from Shop.defaults."""
    try:
        from shopman.models import Shop
        shop = Shop.load()
        if shop:
            return (shop.defaults or {}).get("pickup_slot_config", {})
    except Exception:
        pass
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
        from shopman.crafting.models import WorkOrder
    except ImportError:
        return {}

    cutoff = date.today() - timedelta(days=history_days)

    # Single query: all finished WorkOrders for these SKUs in the window
    wos = (
        WorkOrder.objects.filter(
            output_ref__in=skus,
            status="done",
            finished_at__isnull=False,
            finished_at__date__gte=cutoff,
        )
        .values_list("output_ref", "finished_at")
    )

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
        # No production data — return fallback (first slot)
        fallback = _find_slot_by_ref(slots, fallback_ref) or slots[0]
        return {
            "slot": fallback,
            "slot_ref": fallback["ref"],
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

    # Find the first slot whose starts_at >= latest_time
    sorted_slots = sorted(slots, key=lambda s: _parse_time(s["starts_at"]))
    chosen = sorted_slots[-1]  # default to last slot
    for slot in sorted_slots:
        slot_start = _parse_time(slot["starts_at"])
        if slot_start >= latest_time:
            chosen = slot
            break

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
