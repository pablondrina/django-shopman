"""Crafting Admin with Unfold theme."""

# Lazy imports to avoid circular dependencies
# Import directly from .base when needed:
#   from shopman.craftsman.contrib.admin_unfold.base import BaseModelAdmin

__all__ = [
    "BaseModelAdmin",
    "BaseTabularInline",
    "format_quantity",
]


def __getattr__(name):
    """Lazy import to avoid circular imports during app loading."""
    if name in ("BaseModelAdmin", "BaseTabularInline", "format_quantity"):
        from shopman.craftsman.contrib.admin_unfold.base import (
            BaseModelAdmin,
            BaseTabularInline,
            format_quantity,
        )
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
