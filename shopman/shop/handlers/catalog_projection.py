"""
Catalog projection handler + Offerman signal receivers.

CatalogProjectHandler — processes ``catalog.project_sku`` directives:
  - Checks iFood channel is active.
  - Fetches current ProjectedItem for the SKU from Offerman.
  - Calls IFoodCatalogProjection.project().
  - On 429: schedules retry honoring Retry-After.
  - On other error: exponential backoff (2**attempts minutes), max 5 attempts.

Signal receivers (connected from handlers.__init__._register_catalog_signals):
  on_product_created — fires when Offerman emits ``product_created``.
  on_price_changed   — fires when Offerman emits ``price_changed``.
Both receivers create a ``catalog.project_sku`` Directive (idempotent via
dedupe_key = ``catalog.project_sku:{listing_ref}:{sku}:{content_hash}``).
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from shopman.orderman.models import Directive

from shopman.shop.directives import CATALOG_PROJECT_SKU

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 5


class CatalogProjectHandler:
    """Processes ``catalog.project_sku`` directives for the iFood channel."""

    topic = CATALOG_PROJECT_SKU

    def __init__(self, backend) -> None:
        self._backend = backend

    def handle(self, *, message: Directive, ctx: dict) -> None:
        payload = message.payload
        sku = payload.get("sku")
        listing_ref = payload.get("listing_ref", "ifood")

        if not sku:
            message.status = "failed"
            message.last_error = "missing sku in payload"
            message.save(update_fields=["status", "last_error", "updated_at"])
            return

        # Guard: channel must exist and be active.
        if not _ifood_channel_active():
            logger.info("catalog_projection: ifood channel inactive — skipping sku=%s", sku)
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        # Resolve current ProjectedItem for this SKU.
        item = _get_projected_item(sku, listing_ref)
        if item is None:
            logger.info("catalog_projection: sku=%s not in listing %s — skipping", sku, listing_ref)
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            return

        from shopman.shop.adapters.catalog_projection_ifood import IFoodRateLimitError

        try:
            result = self._backend.project([item], channel="ifood")
        except IFoodRateLimitError as exc:
            message.available_at = timezone.now() + timedelta(seconds=exc.retry_after)
            message.last_error = f"rate_limited retry_after={exc.retry_after}s"
            message.save(update_fields=["available_at", "last_error", "updated_at"])
            logger.info("catalog_projection: rate limited sku=%s retry_after=%ds", sku, exc.retry_after)
            return
        except Exception as exc:
            _handle_transient_error(message, str(exc))
            return

        if result.success:
            message.status = "done"
            message.save(update_fields=["status", "updated_at"])
            logger.info("catalog_projection: done sku=%s projected=%d", sku, result.projected)
        else:
            error_str = "; ".join(result.errors)
            _handle_transient_error(message, error_str)


# ── Signal receivers ──────────────────────────────────────────────────────────


def on_product_created(sender, instance, sku: str, **kwargs) -> None:
    """Enqueue catalog.project_sku for all configured projection listings."""
    for listing_ref in _projection_listing_refs():
        _enqueue_project(sku=sku, listing_ref=listing_ref, trigger="product_created")


def on_price_changed(
    sender,
    instance,
    listing_ref: str,
    sku: str,
    old_price_q,
    new_price_q,
    **kwargs,
) -> None:
    """Enqueue catalog.project_sku when a listing item price changes."""
    if listing_ref not in _projection_listing_refs():
        return
    _enqueue_project(
        sku=sku,
        listing_ref=listing_ref,
        trigger="price_changed",
        extra={"price_q": int(new_price_q)},
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _enqueue_project(
    sku: str,
    listing_ref: str,
    trigger: str,
    extra: dict | None = None,
) -> None:
    data: dict = {"sku": sku, "listing_ref": listing_ref, "trigger": trigger}
    if extra:
        data.update(extra)

    content_hash = hashlib.sha256(
        json.dumps(data, sort_keys=True).encode()
    ).hexdigest()[:16]
    dedupe_key = f"catalog.project_sku:{listing_ref}:{sku}:{content_hash}"

    already_queued = Directive.objects.filter(
        dedupe_key=dedupe_key,
        status__in=["queued", "running"],
    ).exists()
    if already_queued:
        logger.debug(
            "catalog_projection: dedupe skip sku=%s listing=%s trigger=%s",
            sku, listing_ref, trigger,
        )
        return

    Directive.objects.create(
        topic=CATALOG_PROJECT_SKU,
        payload={"sku": sku, "listing_ref": listing_ref},
        dedupe_key=dedupe_key,
    )
    logger.info(
        "catalog_projection: enqueued sku=%s listing=%s trigger=%s",
        sku, listing_ref, trigger,
    )


def _projection_listing_refs() -> list[str]:
    """Return listing refs for all configured catalog projection adapters."""
    adapters = getattr(settings, "SHOPMAN_CATALOG_PROJECTION_ADAPTERS", {})
    return list(adapters.keys())


def _ifood_channel_active() -> bool:
    from shopman.shop.models import Channel
    return Channel.objects.filter(ref="ifood", is_active=True).exists()


def _get_projected_item(sku: str, listing_ref: str):
    """Return the ProjectedItem for ``sku`` in ``listing_ref``, or None."""
    try:
        from shopman.offerman.service import CatalogService
        items = CatalogService.get_projection_items(listing_ref)
        return next((i for i in items if i.sku == sku), None)
    except Exception as exc:
        logger.warning("catalog_projection: error fetching projection items: %s", exc)
        return None


def _handle_transient_error(message: Directive, error: str) -> None:
    message.attempts += 1
    message.last_error = error[:500]
    if message.attempts >= _MAX_ATTEMPTS:
        message.status = "failed"
        logger.error(
            "catalog_projection: terminal failure after %d attempts: %s",
            message.attempts, error,
        )
    else:
        backoff_minutes = 2 ** message.attempts
        message.available_at = timezone.now() + timedelta(minutes=backoff_minutes)
        logger.warning(
            "catalog_projection: transient error attempt=%d backoff=%dmin: %s",
            message.attempts, backoff_minutes, error,
        )
    message.save(update_fields=["status", "attempts", "available_at", "last_error", "updated_at"])
