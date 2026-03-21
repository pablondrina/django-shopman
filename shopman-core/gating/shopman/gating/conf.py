"""
Gating configuration.

Usage in settings.py:
    GATING = {
        "BRIDGE_TOKEN_TTL_MINUTES": 5,
        "MAGIC_CODE_TTL_MINUTES": 10,
        "MESSAGE_SENDER_CLASS": "shopman.gating.senders.ConsoleSender",
    }
"""

import threading
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings


@dataclass
class GatingSettings:
    """Gating configuration settings."""

    # Bridge Token
    BRIDGE_TOKEN_TTL_MINUTES: int = 5

    # Magic Code
    MAGIC_CODE_TTL_MINUTES: int = 10
    MAGIC_CODE_MAX_ATTEMPTS: int = 5
    CODE_RATE_LIMIT_WINDOW_MINUTES: int = 15
    CODE_RATE_LIMIT_MAX: int = 5
    MAGIC_CODE_COOLDOWN_SECONDS: int = 60

    # Sender
    MESSAGE_SENDER_CLASS: str = "shopman.gating.senders.ConsoleSender"

    # WhatsApp Cloud API
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    WHATSAPP_CODE_TEMPLATE: str = "verification_code"

    # URLs
    DEFAULT_DOMAIN: str = "localhost:8000"
    USE_HTTPS: bool = True
    LOGIN_REDIRECT_URL: str = "/"

    # Redirect safety (H02)
    # Hosts allowed in `next` parameter redirects (empty = same-host only)
    ALLOWED_REDIRECT_HOSTS: set[str] = field(default_factory=set)

    # Bridge Token API (H05)
    # Shared secret for authenticating bridge token creation requests.
    # When set, POST /bridge/create/ requires Authorization: Bearer <key>
    # or X-Api-Key: <key> header. Leave empty to skip auth (dev only).
    BRIDGE_TOKEN_API_KEY: str = ""

    # Customer auto-creation (H03)
    # When True, verify_for_login() creates a new Customer if phone not found.
    # When False, login fails if customer doesn't exist.
    AUTO_CREATE_CUSTOMER: bool = True

    # Proxy depth for X-Forwarded-For IP extraction
    # Use 1 for single reverse proxy (Nginx), 2 for CDN + proxy, etc.
    TRUSTED_PROXY_DEPTH: int = 1

    # Session preservation
    # Keys to preserve across login (e.g., basket_session_key for e-commerce)
    PRESERVE_SESSION_KEYS: list[str] | None = None

    # Customer resolver (Protocol-based decoupling from Guestman)
    CUSTOMER_RESOLVER_CLASS: str = "shopman.attending.adapters.gating.AttendingCustomerResolver"

    # Device Trust
    # When True, after OTP verification the user can trust their device
    # to skip OTP on subsequent logins.
    DEVICE_TRUST_ENABLED: bool = True
    DEVICE_TRUST_TTL_DAYS: int = 30
    DEVICE_TRUST_COOKIE_NAME: str = "gating_dt"

    # Magic Link (email-based one-click login)
    MAGIC_LINK_ENABLED: bool = True
    MAGIC_LINK_TTL_MINUTES: int = 15
    MAGIC_LINK_RATE_LIMIT_MAX: int = 5
    MAGIC_LINK_RATE_LIMIT_WINDOW_MINUTES: int = 15

    # Templates (override in your project)
    TEMPLATE_CODE_REQUEST: str = "gating/code_request.html"
    TEMPLATE_CODE_VERIFY: str = "gating/code_verify.html"
    TEMPLATE_BRIDGE_INVALID: str = "gating/bridge_invalid.html"
    TEMPLATE_MAGIC_LINK_REQUEST: str = "gating/magic_link_request.html"
    TEMPLATE_MAGIC_LINK_EMAIL_TXT: str = "gating/email_magic_link.txt"
    TEMPLATE_MAGIC_LINK_EMAIL_HTML: str = "gating/email_magic_link.html"


def get_gating_settings() -> GatingSettings:
    """Load settings from Django settings."""
    user_settings: dict[str, Any] = getattr(settings, "GATING", {})
    return GatingSettings(**user_settings)


class _LazySettings:
    """Lazy proxy that re-reads settings on every attribute access.

    This ensures @override_settings works correctly in tests.
    """

    def __getattr__(self, name):
        return getattr(get_gating_settings(), name)


gating_settings = _LazySettings()


# Customer resolver (singleton, thread-safe)
_customer_resolver = None
_customer_resolver_lock = threading.Lock()


def get_customer_resolver():
    """Get the configured customer resolver (singleton)."""
    global _customer_resolver
    if _customer_resolver is None:
        with _customer_resolver_lock:
            if _customer_resolver is None:
                from django.utils.module_loading import import_string

                s = get_gating_settings()
                cls = import_string(s.CUSTOMER_RESOLVER_CLASS)
                _customer_resolver = cls()
    return _customer_resolver


def reset_customer_resolver():
    """Reset cached resolver. For testing."""
    global _customer_resolver
    _customer_resolver = None
