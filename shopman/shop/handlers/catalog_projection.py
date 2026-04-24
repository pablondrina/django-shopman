"""
Catalog projection handler + Offerman signal receivers.

CatalogProjectHandler — processes ``catalog.project_sku`` directives:
  - Checks iFood channel is active.
  - Resolves the SKU to a ProjectedItem via CatalogService.
  - Calls the backend adapter to push to the external API.
  - Handles 429 rate limiting (honoring Retry-After).
  - Uses DirectiveTransientError for retryable failures.

Signal receivers (on_product_created, on_price_changed) enqueue directives
with SHA-256-based dedupe keys so the same event is never processed twice
while a directive is still queued or running.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta

from django.utils import timezone

from shopman.offerman.protocols.projection import ProjectedItem
from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError
from shopman.orderman.models import Directive
from shopman.shop.directives import CATALOG_PROJECT_SKU

logger = logging.getLogger(__name__)


# ── Handler ───────────────────────────────────────────────────────────────────


class CatalogProjectHandler:
    topic = CATALOG_PROJECT_SKU

    def __init__(self, backend) -> None:
        self.backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload
        sku = payload["sku"]
        listing_ref = payload.get("listing_ref", "ifood")

        if not _ifood_channel_active(listing_ref):
            return

        item = _get_projected_item(sku, listing_ref)
        if item is None:
            return

        from shopman.shop.adapters.catalog_projection_ifood import IFoodRateLimitError

        try:
            result = self.backend.project([item], channel=listing_ref)
        except IFoodRateLimitError as exc:
            # Rate limit: defer with Retry-After from API response
            message.status = "queued"
            message.available_at = timezone.now() + timedelta(seconds=exc.retry_after)
            message.save(update_fields=["status", "available_at", "updated_at"])
            logger.warning(
                "catalog_projection: rate limited for %s/%s, retry in %ds",
                listing_ref, sku, exc.retry_after,
            )
            return

        if result.success:
            return

        raise DirectiveTransientError("; ".join(result.errors))


# ── Helpers ───────────────────────────────────────────────────────────────────


def _ifood_channel_active(listing_ref: str) -> bool:
    from shopman.shop.models import Channel
    return Channel.objects.filter(ref=listing_ref, is_active=True).exists()


def _get_projected_item(sku: str, listing_ref: str) -> ProjectedItem | None:
    from shopman.offerman.service import CatalogService
    items = CatalogService.get_projection_items(listing_ref)
    for item in items:
        if item.sku == sku:
            return item
    return None


def _projection_listing_refs() -> list[str]:
    from django.conf import settings
    return list(getattr(settings, "SHOPMAN_CATALOG_PROJECTION_ADAPTERS", {}).keys())


# ── Signal receivers ──────────────────────────────────────────────────────────


def on_product_created(sender, instance, sku: str, **kwargs) -> None:
    for listing_ref in _projection_listing_refs():
        _enqueue_project(sku, listing_ref, trigger="product_created", extra={})


def on_price_changed(
    sender,
    instance,
    listing_ref: str,
    sku: str,
    old_price_q: int,
    new_price_q: int,
    **kwargs,
) -> None:
    if listing_ref not in _projection_listing_refs():
        return
    _enqueue_project(
        sku,
        listing_ref,
        trigger="price_changed",
        extra={"old_price_q": old_price_q, "new_price_q": new_price_q},
    )


def _enqueue_project(sku: str, listing_ref: str, trigger: str, extra: dict) -> None:
    fingerprint_data = json.dumps({"trigger": trigger, **extra}, sort_keys=True)
    fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
    dedupe_key = f"{CATALOG_PROJECT_SKU}:{listing_ref}:{sku}:{fingerprint}"

    exists = Directive.objects.filter(
        dedupe_key=dedupe_key,
        status__in=("queued", "running"),
    ).exists()
    if exists:
        return

    Directive.objects.create(
        topic=CATALOG_PROJECT_SKU,
        payload={"sku": sku, "listing_ref": listing_ref},
        dedupe_key=dedupe_key,
    )
    logger.debug("catalog_projection: enqueued %s for %s/%s", trigger, listing_ref, sku)
