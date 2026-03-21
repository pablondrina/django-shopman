"""Stocking Admin with Unfold theme."""

# Lazy imports to avoid circular dependencies
# Import directly from shopman.utils when needed:
#   from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin

__all__ = [
    "BaseModelAdmin",
    "BaseTabularInline",
    "format_quantity",
]


def __getattr__(name):
    """Lazy import to avoid circular imports during app loading."""
    if name in ("BaseModelAdmin", "BaseTabularInline"):
        from shopman.utils.contrib.admin_unfold.base import (
            BaseModelAdmin,
            BaseTabularInline,
        )
        return locals()[name]
    if name == "format_quantity":
        from shopman.utils.formatting import format_quantity
        return format_quantity
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
