"""Storefront access-link service."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

SOURCE_TO_ORIGIN = {
    "manychat": "whatsapp",
    "api": "web",
    "internal": "web",
}


def exchange_token(token_str: str, request):
    from shopman.doorman import get_access_link_service

    AccessLinkService = get_access_link_service()
    return AccessLinkService.exchange(
        token_str=token_str,
        request=request,
        preserve_session_keys=["cart_session_key"],
    )


def resolve_origin(result) -> str:
    """Determine origin_channel from exchange result metadata."""
    source = "web"
    try:
        from shopman.doorman.models import AccessLink

        token = (
            AccessLink.objects.filter(
                customer_id=result.customer.uuid,
            )
            .order_by("-created_at")
            .first()
        )
        if token:
            source = token.source
            meta = token.metadata or {}
            if meta.get("channel") == "instagram":
                return "instagram"
            if meta.get("channel") == "whatsapp":
                return "whatsapp"
    except Exception:
        logger.exception("access_link_resolve_origin_failed")

    return SOURCE_TO_ORIGIN.get(source, "web")
