"""Offerman Admin with Unfold theme."""

__all__ = [
    "BaseModelAdmin",
    "BaseTabularInline",
]


def __getattr__(name):
    """Lazy import to avoid circular imports during app loading."""
    if name == "BaseModelAdmin":
        from shopman.utils.contrib.admin_unfold.base import BaseModelAdmin

        return BaseModelAdmin
    if name == "BaseTabularInline":
        from shopman.utils.contrib.admin_unfold.base import BaseTabularInline

        return BaseTabularInline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
