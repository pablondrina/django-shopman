"""
Django signals emitted by shopman.refs operations.

Emitted by: attach(), deactivate(), RefBulk.rename(), transfer().
"""

from django.dispatch import Signal

ref_attached = Signal()
ref_deactivated = Signal()
ref_renamed = Signal()
ref_transferred = Signal()
