"""
Stock alert checker — propagates Stockman StockAlerts to framework OperatorAlerts.

Called explicitly after stock-changing operations (fulfill, issue)
to detect when physical stock drops below configured minimums.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

logger = logging.getLogger(__name__)


def check_and_alert(sku: str | None = None) -> int:
    """Check stock alerts for SKU and create OperatorAlerts for triggered ones.

    Debounce: skips alert creation if an identical stock_low alert was created
    for the same SKU within the last hour.

    Returns count of new OperatorAlerts created.
    """
    try:
        from shopman.stockman.services.alerts import check_alerts
    except ImportError:
        return 0

    triggered = check_alerts(sku=sku)
    if not triggered:
        return 0

    from shopman.shop.models import OperatorAlert

    debounce_cutoff = timezone.now() - timedelta(hours=1)
    created = 0

    for alert, available in triggered:
        # Debounce: skip if recent alert exists for this SKU
        recent = OperatorAlert.objects.filter(
            type="stock_low",
            created_at__gte=debounce_cutoff,
            message__contains=alert.sku,
        ).exists()

        if recent:
            logger.debug(
                "stock_alert: debounced for sku=%s (alert exists within 1h)",
                alert.sku,
            )
            continue

        position_label = str(alert.position) if alert.position else "todas as posições"
        OperatorAlert.objects.create(
            type="stock_low",
            severity="warning",
            message=(
                f"Estoque baixo: {alert.sku} ({available} restantes, "
                f"mínimo {alert.min_quantity}) — {position_label}"
            ),
        )
        created += 1
        logger.info(
            "stock_alert: created operator alert for sku=%s available=%s min=%s",
            alert.sku, available, alert.min_quantity,
        )

    return created
