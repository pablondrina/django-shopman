"""
Guestman signals — public event API.

Emitted signals:
- customer_created: Emitted by services.customer.create()
- customer_updated: Emitted by services.customer.update()
"""

from django.dispatch import Signal

# Customer signals (emitted by services)
customer_created = Signal()  # sender=Customer
customer_updated = Signal()  # sender=Customer, changes=dict
