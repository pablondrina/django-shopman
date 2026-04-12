"""
Craftsman Signals.

Single signal for all production state changes.
Emitted on plan, adjust, start, finish, void.

Usage:
    from shopman.craftsman.signals import production_changed

    @receiver(production_changed)
    def on_production_changed(sender, product_ref, date, **kwargs):
        ...
"""

from django.dispatch import Signal

# Emitted when production state changes (plan, adjust, start, finish, void)
# kwargs: product_ref (str), date (date|None), sender=WorkOrder
production_changed = Signal()

__all__ = ["production_changed"]
