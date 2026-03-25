"""
Shopman Auth — Phone-First Authentication.

Usage:
    from shopman.auth import get_auth_bridge_service, get_verification_service
"""

__title__ = "Shopman Auth"
__version__ = "0.1.0"
__author__ = "Pablo Valentini"


def get_auth_bridge_service():
    """Lazy import to avoid circular imports."""
    from .services.auth_bridge import AuthBridgeService

    return AuthBridgeService


def get_verification_service():
    """Lazy import to avoid circular imports."""
    from .services.verification import AuthService

    return AuthService


def get_auth_service():
    """Lazy import to avoid circular imports."""
    from .services.verification import AuthService

    return AuthService


__all__ = ["get_auth_bridge_service", "get_verification_service", "get_auth_service"]
