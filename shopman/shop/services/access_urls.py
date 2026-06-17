"""AccessUrlService — pre-authenticated magic links for notifications and shares.

Generates an ``AccessLink`` token and wraps it as a **store** entry URL that
authenticates the customer on first click, then lands them on the destination
the backend derives from the token metadata.

Decoupled architecture: the link always points at the Nuxt store
(``SHOPMAN_STOREFRONT_BASE_URL``) — ``…/a?t=<token>`` — so the session cookie is
established on the store host (via the BFF), never on the headless ``api.``
domain. The destination is derived server-side from the token metadata
(``order_ref``/``action``); there is no ``next`` query parameter, so there is no
open-redirect surface.

Usage:
    from shopman.shop.services.access_urls import build_tracking_access_url

    url = build_tracking_access_url(customer, "ORD-001")
    # → https://nelson.com/a?t=abc123
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


def build_access_url(
    customer,
    *,
    source: str = "manychat",
    metadata: dict | None = None,
) -> str | None:
    """Create an AccessLink token and return the full store entry URL.

    Args:
        customer: AuthCustomerInfo with a ``uuid`` field. Returns None if falsy.
        source: Token source tag (e.g. "manychat", "internal").
        metadata: Metadata stored on the AccessLink. The backend derives the
            post-login destination from ``order_ref``/``action``.

    Returns:
        Absolute store entry URL, or None if token creation fails.
    """
    if not customer or not getattr(customer, "uuid", None):
        return None

    try:
        from shopman.doorman.models import AccessLink
        from shopman.doorman.services.access_link import AccessLinkService

        result = AccessLinkService.create_token(
            customer=customer,
            audience=AccessLink.Audience.WEB_GENERAL,
            source=source,
            metadata=metadata or {},
        )
        raw_token = result.token
    except Exception:
        logger.exception("access_urls.build_access_url: token creation failed")
        return None

    from shopman.shop.services import storefront_links

    return storefront_links.storefront_url(
        f"{storefront_links.path_access()}?{urlencode({'t': raw_token})}"
    )


def build_tracking_access_url(customer, order_ref: str, source: str = "manychat") -> str | None:
    """Magic link that lands on the Nuxt order tracking page."""
    return build_access_url(
        customer,
        source=source,
        metadata={"order_ref": order_ref},
    )


def build_payment_access_url(customer, order_ref: str, source: str = "manychat") -> str | None:
    """Magic link that lands on the Nuxt order payment page."""
    return build_access_url(
        customer,
        source=source,
        metadata={"order_ref": order_ref, "action": "payment"},
    )


def build_reorder_access_url(customer, order_ref: str, source: str = "manychat") -> str | None:
    """Magic link that lands on the Nuxt order history (for reordering)."""
    return build_access_url(
        customer,
        source=source,
        metadata={"order_ref": order_ref, "action": "reorder"},
    )
