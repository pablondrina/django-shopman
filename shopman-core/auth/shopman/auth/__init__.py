"""
Shopman Auth — Phone-First Authentication.

Usage:
    from shopman.auth import get_access_link_service, get_auth_service
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


__all__ = ["get_access_link_service", "get_auth_service"]
