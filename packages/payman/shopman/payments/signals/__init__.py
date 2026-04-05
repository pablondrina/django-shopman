"""
Payment Signals.

Sinais emitidos pelo PaymentService durante o lifecycle de um PaymentIntent.

Uso:
    from shopman.payments.signals import payment_captured

    @receiver(payment_captured)
    def on_payment_captured(sender, intent, order_ref, amount_q, **kwargs):
        print(f"Pagamento {intent.ref} capturado: {amount_q}q")

Sinais disponíveis:
    payment_authorized — Intent autorizado (pending → authorized)
    payment_captured   — Intent capturado (authorized → captured)
    payment_failed     — Intent falhou (→ failed)
    payment_cancelled  — Intent cancelado (→ cancelled)
    payment_refunded   — Reembolso registrado (parcial ou total)
"""

from django.dispatch import Signal

# kwargs: intent (PaymentIntent), order_ref (str), amount_q (int), method (str)
payment_authorized = Signal()

# kwargs: intent (PaymentIntent), order_ref (str), amount_q (int), transaction (PaymentTransaction)
payment_captured = Signal()

# kwargs: intent (PaymentIntent), order_ref (str), error_code (str), message (str)
payment_failed = Signal()

# kwargs: intent (PaymentIntent), order_ref (str)
payment_cancelled = Signal()

# kwargs: intent (PaymentIntent), order_ref (str), amount_q (int), transaction (PaymentTransaction)
payment_refunded = Signal()
