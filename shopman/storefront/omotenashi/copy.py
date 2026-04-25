"""Omotenashi copy — re-exported from shopman.shop.omotenashi.copy.

The canonical cache and resolver live in the shop layer so the model
post-save signal (on OmotenashiCopy) reaches a single _DB_CACHE instance.
"""

from shopman.shop.omotenashi.copy import (  # noqa: F401
    AUDIENCE_CHOICES,
    MOMENT_CHOICES,
    OMOTENASHI_DEFAULTS,
    WILDCARD,
    CopyEntry,
    all_keys,
    default_for,
    invalidate_cache,
    resolve_copy,
)
