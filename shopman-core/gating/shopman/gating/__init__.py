"""
Shopman Gating — Phone-First Authentication.

Usage:
    from shopman.gating import get_auth_bridge_service, get_verification_service
"""

__title__ = "Shopman Gating"
__version__ = "0.1.0"
__author__ = "Pablo Valentini"


def get_auth_bridge_service():
    """Lazy import to avoid circular imports."""
    from .services.auth_bridge import AuthBridgeService

    return AuthBridgeService


def get_verification_service():
    """Lazy import to avoid circular imports."""
    from .services.verification import VerificationService

    return VerificationService


__all__ = ["get_auth_bridge_service", "get_verification_service"]
