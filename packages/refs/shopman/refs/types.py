"""
RefType — immutable config-as-code definition of a ref type.

RefTypes are registered in AppConfig.ready() and never stored in the database.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class RefType:
    """
    Definition of a ref type.

    Attributes:
        slug: Unique identifier, UPPER_SNAKE_CASE (e.g. "POS_TABLE", "ORDER_REF").
        label: Human-readable label for UI (e.g. "Mesa", "Referencia do Pedido").

        allowed_targets: Tuple of allowed target types in "{app_label}.{ModelName}" format.
            Use ("*",) to allow any target.

        scope_keys: Required keys in the scope dict for uniqueness partitioning.
        unique_scope: Uniqueness constraint — "active" (unique among active refs only),
            "all" (unique across all states), "none" (no uniqueness enforced).

        normalizer: Value normalization — "upper_strip", "lower_strip", or "none".
        validator: Optional regex pattern applied after normalization.

        generator: Generator slug for auto-value generation ("sequence", "date_sequence",
            "alpha_numeric", "short_uuid"). None means caller must supply the value.
        generator_format: Format string for generated values (e.g. "T-{value:03d}").

        on_deactivate: What happens to refs pointing at a deactivated target —
            "nothing" or "cascade_deactivate".
    """

    slug: str
    label: str

    # Targeting
    allowed_targets: tuple[str, ...] = ("*",)

    # Scope & uniqueness
    scope_keys: tuple[str, ...] = ()
    unique_scope: Literal["active", "all", "none"] = "active"

    # Value handling
    normalizer: Literal["upper_strip", "lower_strip", "none"] = "upper_strip"
    validator: str | None = None

    # Generation (optional)
    generator: str | None = None
    generator_format: str = "{value}"

    # Lifecycle
    on_deactivate: Literal["nothing", "cascade_deactivate"] = "nothing"

    def __post_init__(self) -> None:
        if not self.slug:
            raise ValueError("RefType.slug cannot be empty")
        if not self.slug.replace("_", "").isalnum():
            raise ValueError("RefType.slug must be alphanumeric with underscores")
        if self.unique_scope not in ("active", "all", "none"):
            raise ValueError(f"RefType.unique_scope must be 'active', 'all', or 'none', got '{self.unique_scope}'")
