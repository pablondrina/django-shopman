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
    from shopman.craftsman.signals import production_changed
    from shopman.offerman.models import ListingItem, Product
    from shopman.shop.adapters import alert as alert_adapter
    from shopman.shop.adapters import kds as kds_adapter
    from shopman.orderman.signals import order_changed
    from shopman.stockman.models import Hold, Move

    post_save.connect(_on_hold_saved, sender=Hold, weak=False)
    post_save.connect(_on_move_saved, sender=Move, weak=False)
    pre_save.connect(_track_product_sellable, sender=Product, weak=False)
    post_save.connect(_on_product_saved, sender=Product, weak=False)
    pre_save.connect(_track_listing_item_state, sender=ListingItem, weak=False)
    post_save.connect(_on_listing_item_saved, sender=ListingItem, weak=False)
    kds_ticket_model = kds_adapter.get_ticket_model()
    pre_save.connect(_track_kds_ticket_state, sender=kds_ticket_model, weak=False)
    post_save.connect(_on_kds_ticket_saved, sender=kds_ticket_model, weak=False)
    order_changed.connect(
        _on_order_changed,
        dispatch_uid="shopman.shop.handlers._sse_emitters.on_order_changed",
        weak=False,
    )
    production_changed.connect(
        _on_production_changed,
        dispatch_uid="shopman.shop.handlers._sse_emitters.on_production_changed",
        weak=False,
    )
    alert_adapter.connect_saved(
        _on_operator_alert_saved,
        dispatch_uid="shopman.shop.handlers._sse_emitters.on_operator_alert_saved",
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
    _emit_backstage(
        "orders",
        "backstage-orders-update",
        {"ref": order.ref, "status": order.status, "kind": event_type},
        scope=_scope_for_order(order),
    )


def _on_production_changed(sender, product_ref, date, action, work_order, **kwargs):
    _emit_backstage(
        "production",
        "backstage-production-update",
        {
            "ref": work_order.ref,
            "status": work_order.status,
            "action": action,
            "output_sku": work_order.output_sku,
        },
        scope=_default_backstage_scope(),
    )


def _on_operator_alert_saved(sender, instance, created, **kwargs):
    if not created:
        return
    _emit_backstage(
        "alerts",
        "backstage-alerts-update",
        {
            "id": instance.pk,
            "type": instance.type,
            "severity": instance.severity,
        },
        scope=_default_backstage_scope(),
    )


def emit_kds_change(ticket, *, event_type: str = "backstage-kds-update", scope: str | None = None) -> None:
    """Publish a Backstage KDS event for ticket creation/status/item changes."""
    station_ref = ticket.kds_instance.ref if ticket.kds_instance_id else ""
    payload = {
        "ticket_ref": f"KDS-{ticket.pk}",
        "ticket_id": ticket.pk,
        "kds_instance_ref": station_ref,
        "status": ticket.status,
        "station": station_ref,
        "order_ref": ticket.order.ref if ticket.order_id else "",
        "count_active": _active_kds_count(ticket.kds_instance_id),
    }
    _emit_backstage("kds", event_type, payload, scope=scope or station_ref)


def _track_kds_ticket_state(sender, instance, **kwargs):
    if not instance.pk:
        instance._sse_old_status = None
        instance._sse_old_instance_id = None
        instance._sse_old_items = None
        return
    try:
        old = sender.objects.only("status", "kds_instance_id", "items").get(pk=instance.pk)
        instance._sse_old_status = old.status
        instance._sse_old_instance_id = old.kds_instance_id
        instance._sse_old_items = old.items
    except sender.DoesNotExist:
        instance._sse_old_status = None
        instance._sse_old_instance_id = None
        instance._sse_old_items = None


def _on_kds_ticket_saved(sender, instance, created, **kwargs):
    if created:
        emit_kds_change(instance, event_type="backstage-kds-created")
        emit_kds_change(instance, event_type="backstage-kds-update")
        return
    old_status = getattr(instance, "_sse_old_status", None)
    old_instance_id = getattr(instance, "_sse_old_instance_id", None)
    old_items = getattr(instance, "_sse_old_items", None)
    if old_instance_id and old_instance_id != instance.kds_instance_id:
        emit_kds_change(instance, event_type="backstage-kds-station-changed")
    if old_status is not None and old_status != instance.status:
        emit_kds_change(instance, event_type="backstage-kds-status-changed")
    if old_items is not None and old_items != instance.items:
        emit_kds_change(instance, event_type="backstage-kds-update")
    elif old_status != instance.status or old_instance_id != instance.kds_instance_id:
        emit_kds_change(instance, event_type="backstage-kds-update")


def _active_kds_count(kds_instance_id) -> int:
    if not kds_instance_id:
        return 0
    try:
        from shopman.shop.adapters import kds as kds_adapter

        return kds_adapter.active_ticket_count(kds_instance_id)
    except Exception:
        logger.debug("kds_active_count_failed", exc_info=True)
        return 0


def _emit_backstage(kind: str, event_type: str, payload: dict, *, scope: str | None = None) -> None:
    try:
        from django_eventstream import send_event
    except ImportError:
        logger.warning("django_eventstream not installed; backstage SSE emit skipped")
        return
    try:
        send_event(f"backstage-{kind}-main", event_type, payload)
        if scope and scope != "main":
            send_event(f"backstage-{kind}-{scope}", event_type, payload)
    except Exception:
        logger.warning(
            "Backstage SSE emit failed kind=%s type=%s", kind, event_type, exc_info=True,
        )


def _scope_for_order(order) -> str:
    try:
        from shopman.shop.models import Channel

        channel = Channel.objects.select_related("shop").filter(ref=order.channel_ref).first()
        if channel and channel.shop_id:
            return f"shop-{channel.shop_id}"
    except Exception:
        logger.debug("backstage_sse.order_scope_failed order=%s", getattr(order, "ref", ""), exc_info=True)
    return _default_backstage_scope()


def _default_backstage_scope() -> str:
    try:
        from shopman.shop.models import Shop

        shop = Shop.objects.only("pk").first()
        return f"shop-{shop.pk}" if shop else "main"
    except Exception:
        logger.debug("backstage_sse.default_scope_failed", exc_info=True)
        return "main"


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
