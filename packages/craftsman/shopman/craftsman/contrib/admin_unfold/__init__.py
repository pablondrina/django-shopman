"""Craftsman Admin with Unfold theme."""

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
    if name == "BaseModelAdmin":
        from shopman.craftsman.contrib.admin_unfold.base import BaseModelAdmin

        return BaseModelAdmin
    if name == "BaseTabularInline":
        from shopman.craftsman.contrib.admin_unfold.base import BaseTabularInline

        return BaseTabularInline
    if name == "format_quantity":
        from shopman.craftsman.contrib.admin_unfold.base import format_quantity

        return format_quantity
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
