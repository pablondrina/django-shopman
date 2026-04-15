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

from .catalog import (
    CatalogItemProjection,
    CatalogProjection,
    CatalogSectionProjection,
    build_catalog,
)
from .types import Availability, CategoryProjection, HappyHourProjection

__all__ = [
    "Availability",
    "CatalogItemProjection",
    "CatalogProjection",
    "CatalogSectionProjection",
    "CategoryProjection",
    "HappyHourProjection",
    "build_catalog",
]
