"""
Topic constants — canonical names for all directive topics.

Every handler, hook, and preset should use these constants instead of
magic strings. This is the single source of truth for topic names.
"""

# Stock
STOCK_HOLD = "stock.hold"
STOCK_COMMIT = "stock.commit"
STOCK_RELEASE = "stock.release"

# Payment
PAYMENT_CAPTURE = "payment.capture"
PAYMENT_REFUND = "payment.refund"
PIX_GENERATE = "pix.generate"
PIX_TIMEOUT = "pix.timeout"
PAYMENT_TIMEOUT = "payment.timeout"
CARD_CREATE = "card.create"

# Notification
NOTIFICATION_SEND = "notification.send"

# Fulfillment
FULFILLMENT_CREATE = "fulfillment.create"
FULFILLMENT_UPDATE = "fulfillment.update"

# Confirmation
CONFIRMATION_TIMEOUT = "confirmation.timeout"

# Customer
CUSTOMER_ENSURE = "customer.ensure"

# Fiscal
FISCAL_EMIT_NFCE = "fiscal.emit_nfce"
FISCAL_CANCEL_NFCE = "fiscal.cancel_nfce"

# Accounting
ACCOUNTING_CREATE_PAYABLE = "accounting.create_payable"

# Loyalty
LOYALTY_EARN = "loyalty.earn"

# Checkout defaults
CHECKOUT_INFER_DEFAULTS = "checkout.infer_defaults"

# Returns
RETURN_PROCESS = "return.process"
