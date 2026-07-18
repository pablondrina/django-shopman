"""Social PIM contrib — per-product attributes for social/commerce catalogs.

Stores the fields the external platforms (Meta/Instagram/Facebook/WhatsApp,
Google Shopping, TikTok Shop) require — brand, GTIN, condition, taxonomic
category, hashtags, social caption — as a typed dataclass in
``Product.metadata['social']``. No Core migration: same pattern as
``nutrition_facts`` and ``metadata['fiscal']`` (Fiscalman).

Read/write helpers: :func:`get_social_attributes` / :func:`set_social_attributes`.
Schema + validation: :class:`ProductSocialAttributes`.
"""

from __future__ import annotations

from shopman.offerman.contrib.social.schema import (
    CONDITION_CHOICES,
    ProductSocialAttributes,
    get_social_attributes,
    set_social_attributes,
)

__all__ = [
    "CONDITION_CHOICES",
    "ProductSocialAttributes",
    "get_social_attributes",
    "set_social_attributes",
]
