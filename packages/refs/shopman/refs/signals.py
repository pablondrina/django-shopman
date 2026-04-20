"""
Django signals for shopman.refs lifecycle events.

Signals are sent after the DB operation completes (still inside the transaction
for atomic operations). Receivers that need post-commit guarantees should use
transaction.on_commit() internally.
"""

from django.dispatch import Signal

# Sent by services.attach() when a new Ref is created.
# kwargs: ref (Ref instance), actor (str)
ref_attached = Signal()

# Sent by services.deactivate() and RefBulk.deactivate_scope() per ref.
# kwargs: ref (Ref instance), actor (str)
ref_deactivated = Signal()

# Sent by RefBulk.rename() per updated Ref.
# kwargs: ref (Ref instance with new value), old_value (str), actor (str)
ref_renamed = Signal()

# Sent by services.transfer() after all refs are moved.
# kwargs: refs (list[Ref]), source (str), dest (str), actor (str)
ref_transferred = Signal()
