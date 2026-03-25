"""
Auth services.
"""

from .auth_bridge import AuthBridgeService
from .device_trust import DeviceTrustService
from .magic_link import MagicLinkService
from .verification import AuthService, VerificationService

__all__ = [
    "AuthBridgeService",
    "AuthService",
    "DeviceTrustService",
    "MagicLinkService",
    "VerificationService",
]
