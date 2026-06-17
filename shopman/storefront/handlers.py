"""Storefront signal receivers.

Stock-back alerts ("Me avise"): when a Stockman ``Move`` lands for a SKU that has
pending alert subscriptions, schedule the notify pass to run *after* the move's
transaction commits (so the new stock is visible and we don't send inside the txn).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def on_move_for_stock_alerts(sender, instance, **kwargs) -> None:
    quant_id = getattr(instance, "quant_id", None)
    if not quant_id:
        return
    sku = getattr(getattr(instance, "quant", None), "sku", None)
    if not sku:
        return

    from shopman.storefront.services import stock_alerts

    # Fast path: skip unless someone is actually waiting on this SKU.
    if not stock_alerts.has_pending(sku):
        return

    from django.db import transaction

    transaction.on_commit(lambda: stock_alerts.notify_back_in_stock(sku))
