"""
shopman.refs — public API.

Usage:
    from shopman.refs import attach, resolve, deactivate, transfer
    from shopman.refs import register_ref_type, get_ref_type
    from shopman.refs.types import RefType
"""

# Registry functions are safe to import eagerly (no models involved)
from shopman.refs.registry import get_all_ref_types, get_ref_type, register_ref_type

default_app_config = "shopman.refs.apps.RefsConfig"

_LAZY_NAMES = frozenset({
    # Services
    "attach",
    "resolve",
    "resolve_partial",
    "resolve_object",
    "deactivate",
    "transfer",
    "refs_for",
    "target_str",
    "parse_target",
    # Bulk
    "RefBulk",
})


def __getattr__(name):
    """Lazy import to avoid AppRegistryNotReady during app loading."""
    if name in _LAZY_NAMES:
        if name == "RefBulk":
            from shopman.refs.bulk import RefBulk
            return RefBulk
        from shopman.refs import services
        return getattr(services, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    # Registry
    "register_ref_type",
    "get_ref_type",
    "get_all_ref_types",
    # Services (lazily loaded)
    "attach",
    "resolve",
    "resolve_partial",
    "resolve_object",
    "deactivate",
    "transfer",
    "refs_for",
    # Helpers
    "target_str",
    "parse_target",
    # Bulk operations (lazily loaded)
    "RefBulk",
]
