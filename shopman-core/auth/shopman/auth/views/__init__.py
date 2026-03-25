"""
Auth views.
"""

from .bridge import BridgeTokenCreateView, BridgeTokenExchangeView
from .magic_code import MagicCodeRequestView, MagicCodeVerifyView
from .magic_link import MagicLinkRequestView

__all__ = [
    "BridgeTokenCreateView",
    "BridgeTokenExchangeView",
    "MagicCodeRequestView",
    "MagicCodeVerifyView",
    "MagicLinkRequestView",
]
