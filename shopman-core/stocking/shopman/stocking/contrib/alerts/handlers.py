"""
Signal handlers for stock alert dispatch.

Connects to Move.post_save to reactively check alerts when stock changes.
Uses transaction.on_commit to ensure Quant._quantity is already updated
before checking alerts (Move.save() updates Quant after super().save()).
"""

from __future__ import annotations

import logging
from datetime import timedelta
from functools import partial

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from shopman.stocking.models.move import Move

from .conf import get_alert_cooldown_minutes

logger = logging.getLogger("shopman.stocking")


@receiver(post_save, sender=Move)
def on_move_created(sender, instance, created, **kwargs):
    """
    When a Move is created, schedule alert check after transaction commits.

    Uses on_commit to ensure the Quant._quantity F() update has been applied
    before checking stock levels against alert thresholds.
    """
    if not created:
        return

    move = instance
    quant = move.quant

    transaction.on_commit(
        partial(
            _check_alerts_for_sku,
            sku=quant.sku,
        )
    )


def _check_alerts_for_sku(sku: str) -> None:
    """
    Check and dispatch alerts for a specific SKU.

    Checks cooldown BEFORE calling check_alerts() (which updates
    last_triggered_at). Respects cooldown to prevent flooding.
    """
    from shopman.stocking.models.alert import StockAlert
    from shopman.stocking.services.alerts import check_alerts

    cooldown_minutes = get_alert_cooldown_minutes()
    now = timezone.now()
    cooldown_threshold = now - timedelta(minutes=cooldown_minutes)

    # Filter to alerts that are active AND past cooldown
    alerts = StockAlert.objects.filter(
        sku=sku,
        is_active=True,
    )

    if not alerts.exists():
        return

    # Check cooldown: skip alerts recently triggered
    eligible_alerts = []
    for alert in alerts.select_related("position"):
        if alert.last_triggered_at and alert.last_triggered_at > cooldown_threshold:
            logger.debug(
                "stock.alert.cooldown: alert_id=%s, last_triggered=%s, skipping",
                alert.pk,
                alert.last_triggered_at,
            )
            continue
        eligible_alerts.append(alert)

    if not eligible_alerts:
        return

    # check_alerts updates last_triggered_at on triggered alerts
    triggered = check_alerts(sku=sku)

    eligible_pks = {a.pk for a in eligible_alerts}
    for alert, available in triggered:
        if alert.pk in eligible_pks:
            _dispatch_notification(alert, available)


def _dispatch_notification(alert, available) -> None:
    """
    Create a Directive for notification if Omniman is available.

    Graceful: logs and returns if Omniman is not installed.
    """
    try:
        from omniman.models import Directive

        position_str = alert.position.ref if alert.position else "all"

        Directive.objects.create(
            topic="notification.send",
            payload={
                "event": "stock.alert.triggered",
                "context": {
                    "alert_id": alert.pk,
                    "sku": alert.sku,
                    "position": position_str,
                    "min_quantity": str(alert.min_quantity),
                    "available": str(available),
                },
            },
        )

        logger.info(
            "stock.alert.dispatched: alert_id=%s, sku=%s, available=%s",
            alert.pk,
            alert.sku,
            available,
        )

    except ImportError:
        logger.debug("Omniman not available, skipping alert dispatch for alert_id=%s", alert.pk)
    except Exception:
        logger.warning(
            "Failed to create Directive for alert_id=%s",
            alert.pk,
            exc_info=True,
        )
