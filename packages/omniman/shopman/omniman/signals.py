"""
Omniman Signals — Sinais Django para eventos do sistema.

Sinais emitidos:
- order_changed: Quando Order é criado ou muda de status.

Uso:
    from shopman.omniman.signals import order_changed

    @receiver(order_changed)
    def on_order_changed(sender, order, event_type, actor, **kwargs):
        print(f"Order {order.ref} — {event_type} by {actor}")
"""

from django.dispatch import Signal

# Emitido quando Order é criado ou muda de status.
# kwargs: order (Order), event_type (str), actor (str)
order_changed = Signal()
