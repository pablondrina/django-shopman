"""Projections — typed read models.

Projections translate domain state into what the UI (and later, the API) needs
to consume. Views call a builder, pass the result to the template. Templates
consume a stable interface instead of domain model internals.

Rules:
- Projections are read-only and immutable (frozen dataclasses)
- Never expose PKs, querysets, or model instances
- Monetary values are dual: raw (`_q` in cents) + display (pre-formatted string)
- Availability is a canonical enum, not a bool
"""

from .cart import (
    CartItemProjection,
    CartProjection,
    DiscountLineProjection,
    MinimumOrderProgressProjection,
    UpsellSuggestionProjection,
    build_cart,
)
from .catalog import (
    CatalogItemProjection,
    CatalogProjection,
    CatalogSectionProjection,
    build_catalog,
    build_catalog_items_for_skus,
)
from .product_detail import (
    AllergenInfoProjection,
    ConservationInfoProjection,
    ProductDetailProjection,
    build_product_detail,
)
from .types import (
    Availability,
    CategoryProjection,
    ComponentProjection,
    HappyHourProjection,
)

__all__ = [
    "AllergenInfoProjection",
    "Availability",
    "CartItemProjection",
    "CartProjection",
    "CatalogItemProjection",
    "CatalogProjection",
    "CatalogSectionProjection",
    "CategoryProjection",
    "ComponentProjection",
    "ConservationInfoProjection",
    "DiscountLineProjection",
    "HappyHourProjection",
    "MinimumOrderProgressProjection",
    "ProductDetailProjection",
    "UpsellSuggestionProjection",
    "build_cart",
    "build_catalog",
    "build_catalog_items_for_skus",
    "build_product_detail",
]
