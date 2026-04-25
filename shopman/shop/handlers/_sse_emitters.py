"""
SSE emitters — publish availability changes to subscribed clients.

Each event is published per sales channel (one SSE channel per ``Channel.ref``
listing the affected SKU). Payloads carry only ``sku`` plus the bare minimum
state diff; clients refetch the canonical partial via the existing endpoints,
keeping ``availability.check`` as the single source of truth.

Wired in ``shopman.shop.handlers.__init__._register_sse_emitters`` and only
active when ``django_eventstream`` is installed (it is, since WP-AV-10).
"""

from __future__ import annotations

import logging

from django.core.cache import cache
from django.db.models.signals import post_save, pre_save

logger = logging.getLogger(__name__)


# ── Channel resolution ──────────────────────────────────────────────


def _channels_for_sku(sku: str) -> list[str]:
    """Return the ``Channel.ref`` values whose Listing exposes this SKU.

    Listings are coupled to channels by convention (``Listing.ref ==
    Channel.ref``), so we resolve membership through ``ListingItem`` filtered
    by active listings only. Falls back to every active channel when the SKU
    has no Listing yet (rare — products created before listing setup).
    """
    from shopman.offerman.models import ListingItem

    from shopman.shop.models import Channel

    refs = (
        ListingItem.objects.filter(
            product__sku=sku,
            listing__is_active=True,
        )
        .values_list("listing__ref", flat=True)
        .distinct()
    )
    refs = [ref for ref in refs if ref]
    if refs:
        return refs
    return list(
        Channel.objects.filter(is_active=True).values_list("ref", flat=True)
    )


# ── Emit helper ──────────────────────────────────────────────────────


def _emit_for_sku(sku: str, *, event_type: str, extra: dict | None = None) -> None:
    """Publish an SSE event for ``sku`` to every channel that lists it.

    Also invalidates the per-channel availability cache so the next API read
    sees fresh data — without this, push updates would race the 10s cache TTL
    in :mod:`shopman.shop.api.availability`.
    """
    if not sku:
        return

    payload = {"sku": sku, **(extra or {})}
    try:
        from django_eventstream import send_event
    except ImportError:
        logger.warning("django_eventstream not installed; SSE emit skipped")
        return

    try:
        channel_refs = _channels_for_sku(sku)
        for ref in channel_refs:
            cache.delete(f"availability:{sku}:{ref}")
            send_event(f"stock-{ref}", event_type, payload)
        cache.delete(f"availability:{sku}:default")
    except Exception:
        logger.warning(
            "SSE emit failed sku=%s type=%s", sku, event_type, exc_info=True,
        )


# ── Signal receivers ────────────────────────────────────────────────


def _connect() -> None:
    """Wire post_save / pre_save receivers. Called once from ``register_all``."""
    from shopman.offerman.models import ListingItem, Product
    from shopman.orderman.signals import order_changed
    from shopman.stockman.models import Hold, Move

    post_save.connect(_on_hold_saved, sender=Hold, weak=False)
    post_save.connect(_on_move_saved, sender=Move, weak=False)
    pre_save.connect(_track_product_sellable, sender=Product, weak=False)
    post_save.connect(_on_product_saved, sender=Product, weak=False)
    pre_save.connect(_track_listing_item_state, sender=ListingItem, weak=False)
    post_save.connect(_on_listing_item_saved, sender=ListingItem, weak=False)
    order_changed.connect(
        _on_order_changed,
        dispatch_uid="shopman.shop.handlers._sse_emitters.on_order_changed",
        weak=False,
    )
    logger.info("shopman.handlers: SSE emitters connected.")


# ── Order tracking events ────────────────────────────────────────────


def _emit_for_order(order_ref: str, *, event_type: str, payload: dict | None = None) -> None:
    """Publish an SSE event on the per-order channel ``order-{ref}``.

    Tracking pages subscribe to this channel so customers see status
    transitions live without HTMX polling.
    """
    if not order_ref:
        return
    try:
        from django_eventstream import send_event
    except ImportError:
        logger.warning("django_eventstream not installed; SSE order emit skipped")
        return
    try:
        send_event(f"order-{order_ref}", event_type, payload or {"ref": order_ref})
    except Exception:
        logger.warning(
            "SSE order emit failed ref=%s type=%s", order_ref, event_type, exc_info=True,
        )


def _on_order_changed(sender, order, event_type, actor, **kwargs):
    if event_type not in ("created", "status_changed"):
        return
    _emit_for_order(
        order.ref,
        event_type="order-update",
        payload={"ref": order.ref, "status": order.status, "kind": event_type},
    )


# Hold and Move always represent stock motion — emit unconditionally.


def _on_hold_saved(sender, instance, **kwargs):
    _emit_for_sku(instance.sku, event_type="stock-update")


def _on_move_saved(sender, instance, **kwargs):
    if not instance.quant_id:
        return
    sku = getattr(instance.quant, "sku", None)
    if sku:
        _emit_for_sku(sku, event_type="stock-update")


def _track_product_sellable(sender, instance, **kwargs):
    """Snapshot the previous ``is_sellable`` value so post_save can diff it."""
    if not instance.pk:
        instance._sse_was_sellable = None
        return
    try:
        old = sender.objects.only("is_sellable").get(pk=instance.pk)
        instance._sse_was_sellable = old.is_sellable
    except sender.DoesNotExist:
        instance._sse_was_sellable = None


def _on_product_saved(sender, instance, created, **kwargs):
    previous = getattr(instance, "_sse_was_sellable", None)
    if created or previous is None or previous == instance.is_sellable:
        return
    _emit_for_sku(
        instance.sku,
        event_type="product-paused",
        extra={"is_sellable": instance.is_sellable},
    )


def _track_listing_item_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._sse_was_published = None
        instance._sse_was_sellable = None
        return
    try:
        old = sender.objects.only("is_published", "is_sellable").get(pk=instance.pk)
        instance._sse_was_published = old.is_published
        instance._sse_was_sellable = old.is_sellable
    except sender.DoesNotExist:
        instance._sse_was_published = None
        instance._sse_was_sellable = None


def _on_listing_item_saved(sender, instance, created, **kwargs):
    prev_pub = getattr(instance, "_sse_was_published", None)
    prev_sell = getattr(instance, "_sse_was_sellable", None)
    if created:
        return
    changed = (
        prev_pub is not None and prev_pub != instance.is_published
    ) or (
        prev_sell is not None and prev_sell != instance.is_sellable
    )
    if not changed:
        return
    sku = instance.product.sku
    _emit_for_sku(sku, event_type="listing-changed")
