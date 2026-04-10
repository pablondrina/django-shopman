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

# Confirmation
CONFIRMATION_TIMEOUT = "confirmation.timeout"


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


# ── Queue helper ──


def queue(topic, order, **extra):
    """
    Create a Directive for async processing.

    Always includes order_ref and channel_ref. Extra kwargs are
    merged into the payload.

    Usage:
        from shopman import directives
        directives.queue("notification.send", order, template="order_confirmed")
    """
    payload = {"order_ref": order.ref}
    if order.channel_ref:
        payload["channel_ref"] = order.channel_ref
    payload.update(extra)
    return Directive.objects.create(topic=topic, payload=payload)
