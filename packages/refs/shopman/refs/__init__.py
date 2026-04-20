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

_SERVICE_NAMES = frozenset({
    "attach",
    "resolve",
    "resolve_partial",
    "resolve_object",
    "deactivate",
    "transfer",
    "refs_for",
    "target_str",
    "parse_target",
})


def __getattr__(name):
    """Lazy import of service functions to avoid AppRegistryNotReady during app loading."""
    if name in _SERVICE_NAMES:
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
]
