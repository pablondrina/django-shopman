"""
DeepLinkService — pre-authenticated bridge URLs for notifications and share buttons.

Generates AccessLink tokens and wraps them as bridge URLs that authenticate
the customer on first click, then redirect to the intended destination.

Usage:
    from shopman.shop.services.deep_links import build_bridge_url

    url = build_bridge_url(request, customer, next_url="/pedido/ORD-001/")
    # → https://example.com/bridge/?t=abc123&next=/pedido/ORD-001/

    # Without a request (e.g. from async notification handlers):
    url = build_bridge_url(None, customer, next_url="/pedido/ORD-001/")
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


def build_bridge_url(
    request_or_shop,
    customer,
    next_url: str = "/menu/",
    source: str = "manychat",
    metadata: dict | None = None,
) -> str | None:
    """
    Create an AccessLink token and return the full bridge URL.

    Args:
        request_or_shop: HttpRequest for absolute URL building, or None to use
                         the Sites framework domain.
        customer: AuthCustomerInfo with uuid field. Returns None if falsy.
        next_url: Destination path after authentication.
        source: Token source tag (e.g. "manychat", "internal").
        metadata: Optional metadata stored on the AccessLink.

    Returns:
        Full bridge URL string, or None if token creation fails.
    """
    if not customer or not getattr(customer, "uuid", None):
        return None

    try:
        from shopman.doorman.services.access_link import AccessLinkService
        from shopman.doorman.models import AccessLink

        result = AccessLinkService.create_token(
            customer=customer,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=source,
            metadata=metadata or {},
        )
        raw_token = result.token

    except Exception:
        logger.exception("deep_links.build_bridge_url: token creation failed")
        return None

    domain = _resolve_domain(request_or_shop)
    params = urlencode({"t": raw_token, "next": next_url})
    return f"{domain}/bridge/?{params}"


def build_tracking_url(request_or_shop, customer, order_ref: str, source: str = "manychat") -> str | None:
    """Shortcut for building an authenticated tracking deep link."""
    return build_bridge_url(
        request_or_shop,
        customer,
        next_url=f"/pedido/{order_ref}/",
        source=source,
        metadata={"order_ref": order_ref},
    )


def build_reorder_url(request_or_shop, customer, order_ref: str, source: str = "manychat") -> str | None:
    """Shortcut for building an authenticated reorder deep link."""
    return build_bridge_url(
        request_or_shop,
        customer,
        next_url=f"/meus-pedidos/{order_ref}/reorder/",
        source=source,
        metadata={"order_ref": order_ref, "action": "reorder"},
    )


# ── private helpers ──

def _resolve_domain(request_or_shop) -> str:
    """Return protocol+domain string for URL construction."""
    from django.http import HttpRequest

    if isinstance(request_or_shop, HttpRequest):
        return request_or_shop.build_absolute_uri("/").rstrip("/")

    # Async context — use Sites framework
    try:
        from django.contrib.sites.models import Site
        from shopman.doorman.conf import doorman_settings

        domain = Site.objects.get_current().domain
        protocol = "https" if doorman_settings.USE_HTTPS else "http"
        return f"{protocol}://{domain}"
    except Exception:
        pass

    # Final fallback
    try:
        from django.conf import settings
        return getattr(settings, "SHOPMAN_BASE_URL", "https://localhost:8000")
    except Exception:
        return "https://localhost:8000"
