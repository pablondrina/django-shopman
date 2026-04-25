"""Guestman Admin with Unfold theme."""

# Lazy imports to avoid circular dependencies
# Import directly from .base when needed:
#   from shopman.guestman.contrib.admin_unfold.base import BaseModelAdmin

__all__ = [
    "BaseModelAdmin",
    "BaseTabularInline",
]


def __getattr__(name):
    """Lazy import to avoid circular imports during app loading."""
    if name == "BaseModelAdmin":
        from shopman.guestman.contrib.admin_unfold.base import BaseModelAdmin

        return BaseModelAdmin
    if name == "BaseTabularInline":
        from shopman.guestman.contrib.admin_unfold.base import BaseTabularInline

        return BaseTabularInline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
