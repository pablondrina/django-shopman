"""Storefront signal receivers.

Alerts do cliente ("Me avise"), dois gatilhos:

- ``stock_back`` — um ``Move`` do Stockman pousa para um SKU com inscrições
  pendentes;
- ``production_ready`` — uma fornada (``production_changed``, action=finished)
  conclui para esse SKU.

Nos dois casos o envio é agendado para *depois* do commit da transação, para
que o estoque novo já esteja visível quando o aviso prometer "pode pedir".
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
    if not stock_alerts.has_pending(sku, alert_type="stock_back"):
        return

    from django.db import transaction

    transaction.on_commit(lambda: stock_alerts.notify_back_in_stock(sku))


def on_production_finished_for_stock_alerts(
    sender, product_ref, date, action, work_order, **kwargs
) -> None:
    """Avisar quem pediu "me avise quando sair do forno" (F9)."""
    if action != "finished" or not product_ref:
        return

    from shopman.storefront.services import stock_alerts

    if not stock_alerts.has_pending(product_ref, alert_type="production_ready"):
        return

    from django.db import transaction

    transaction.on_commit(lambda: stock_alerts.notify_bake_ready(product_ref))
