"""Storefront merchandising — Presentation helpers.

Renders merchandising data (freshness, …) into display strings. Consumes the
data Projection plus the copy catalog; resolves copy via ``OmotenashiCopy`` and
owns the display-granularity choices (e.g. the 15-minute freshness bucket). No
policy: *which* items are fresh (the lookback window) is decided in the data
layer; this module only decides *how* the age is shown.
"""

from __future__ import annotations

import math

from shopman.shop.projections.copy import build_copy

_FRESH_BUCKET_MINUTES = 15  # display granularity (rounded up)
_FRESH_BUCKET_CAP = 60      # never show more precise than "há 1h"


def freshness_label(minutes_ago: float) -> str:
    """Render a freshness badge label from a raw age in minutes.

    Rounds the age up to the nearest 15-minute bucket, capped at 1 h, and
    resolves the copy from ``OmotenashiCopy`` (``STOREFRONT_FRESHNESS_*``).
    """
    bucket = min(math.ceil(minutes_ago / _FRESH_BUCKET_MINUTES) * _FRESH_BUCKET_MINUTES, _FRESH_BUCKET_CAP)
    if bucket <= 0:
        bucket = _FRESH_BUCKET_MINUTES
    copy = build_copy("STOREFRONT")
    if bucket >= _FRESH_BUCKET_CAP:
        return copy.message("STOREFRONT_FRESHNESS_HOUR", "há 1h")
    return copy.message("STOREFRONT_FRESHNESS_RECENT", "há {minutes} min").format(minutes=bucket)


__all__ = ["freshness_label"]
