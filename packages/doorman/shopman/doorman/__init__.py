"""
Shopman Auth — Phone-First Authentication.

Usage:
    from shopman.doorman import get_access_link_service, get_auth_service
"""

__title__ = "Shopman Auth"
__version__ = "0.1.0"
__author__ = "Pablo Valentini"


def get_access_link_service():
    """Lazy import to avoid circular imports."""
    from .services.access_link import AccessLinkService

    return AccessLinkService


def get_auth_service():
    """Lazy import to avoid circular imports."""
    from .services.verification import AuthService

    return AuthService


def __getattr__(name):
    """Lazy import for public surfaces."""
    if name == 'TrustedDevice':
        from shopman.doorman.models.device_trust import TrustedDevice
        return TrustedDevice
    elif name == 'hash_device_token':
        from shopman.doorman.models.device_trust import _hash_token
        return _hash_token
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "get_access_link_service",
    "get_auth_service",
    "TrustedDevice",
    "hash_device_token",
]
