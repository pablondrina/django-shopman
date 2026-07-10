"""
Directives — topic constants + queue helper.

Topic constants: canonical names for all directive topics (single source of truth).
queue(): single entry point for creating Directives across services.
"""

from shopman.orderman.models import Directive

# ── Topic constants ──

# Notification
NOTIFICATION_SEND = "notification.send"

# Fulfillment
FULFILLMENT_CREATE = "fulfillment.create"
FULFILLMENT_UPDATE = "fulfillment.update"
# Rede de segurança: auto-conclui um pedido em entrega após ETA + folga, se nem
# o cliente ("Recebi") nem o operador ("Marcar entregue") fecharem o loop.
DELIVERY_AUTO_COMPLETE = "delivery.auto_complete"

# Courier (logística externa — Machine)
# Despacho da corrida ao marcar "pronto" (retry/idempotência via Directive) e
# heartbeat de polling do status (fallback do webhook, auto-reagendável).
COURIER_DISPATCH = "courier.dispatch"
COURIER_SYNC = "courier.sync"

# Confirmation
CONFIRMATION_TIMEOUT = "confirmation.timeout"
ORDER_STALE_NEW_ALERT = "order.stale_new_alert"

# Payment
PAYMENT_TIMEOUT = "payment.timeout"
PAYMENT_REFUND = "payment.refund"  # retry assíncrono de estorno com backoff

# Production
# Heartbeat auto-reagendável: varre WOs started além da janela e planned
# esquecidas, criando OperatorAlerts sem depender de tela aberta.
PRODUCTION_LATE_CHECK = "production.late_check"


# Fiscal
FISCAL_EMIT_NFCE = "fiscal.emit_nfce"
FISCAL_CANCEL_NFCE = "fiscal.cancel_nfce"

# Accounting
ACCOUNTING_CREATE_PAYABLE = "accounting.create_payable"

# Loyalty
LOYALTY_EARN = "loyalty.earn"
LOYALTY_REDEEM = "loyalty.redeem"

# Returns
RETURN_PROCESS = "return.process"

# Catalog projection
CATALOG_PROJECT_SKU = "catalog.project_sku"

# iFood status callback (push internal lifecycle → iFood order actions)
IFOOD_STATUS_CALLBACK = "ifood.status_callback"


# ── Queue helper ──


def queue(topic, order, **extra):
    """
    Create a Directive for async processing.

    Always includes order_ref and channel_ref. Extra kwargs are
    merged into the payload.

    Usage:
        from shopman.shop import directives
        directives.queue("notification.send", order, template="order_confirmed")
    """
    payload = {"order_ref": order.ref}
    if order.channel_ref:
        payload["channel_ref"] = order.channel_ref
    payload.update(extra)
    return Directive.objects.create(topic=topic, payload=payload)
