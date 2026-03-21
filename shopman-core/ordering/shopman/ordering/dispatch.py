"""
Signal-driven directive dispatch.

Processes newly created directives immediately via post_save signal,
with opportunistic retry of failed directives from the same topic.
"""
from __future__ import annotations

import logging
import threading
from datetime import timedelta

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
OPPORTUNISTIC_RETRY_LIMIT = 3

# Thread-local reentrancy guard: prevents cascading dispatch when a handler
# creates new directives via Directive.objects.create() during execution.
_local = threading.local()


def _backoff_seconds(attempts: int) -> int:
    """Exponential backoff: 2^attempts seconds."""
    return 2 ** attempts


def _process_directive(directive) -> None:
    """
    Process a single directive using its registered handler.

    On success: marks as "done" (handler is responsible for setting status).
    On failure: marks as "queued" with backoff, or "failed" if max attempts reached.
    """
    from shopman.ordering import registry

    handler = registry.get_directive_handler(directive.topic)
    if not handler:
        logger.warning("No handler registered for topic %s, leaving queued.", directive.topic)
        return

    now = timezone.now()
    directive.status = "running"
    directive.attempts += 1
    directive.started_at = now
    directive.save(update_fields=["status", "attempts", "started_at", "updated_at"])

    _local.dispatching = True
    try:
        handler.handle(message=directive, ctx={"actor": "signal_dispatch"})
    except Exception as exc:
        logger.exception(
            "Directive %s #%s failed (attempt %d/%d)",
            directive.topic, directive.pk, directive.attempts, MAX_ATTEMPTS,
        )
        if directive.attempts >= MAX_ATTEMPTS:
            directive.status = "failed"
        else:
            directive.status = "queued"
            directive.available_at = now + timedelta(seconds=_backoff_seconds(directive.attempts))
        directive.last_error = str(exc)[:500]
        directive.save(update_fields=["status", "available_at", "last_error", "updated_at"])
    finally:
        _local.dispatching = False


def _retry_failed_directives(topic: str) -> None:
    """
    Opportunistic retry: sweep up to OPPORTUNISTIC_RETRY_LIMIT failed/queued
    directives for the same topic whose available_at has passed.
    """
    from shopman.ordering.models import Directive

    now = timezone.now()

    with transaction.atomic():
        retryable = (
            Directive.objects
            .select_for_update(skip_locked=True)
            .filter(
                topic=topic,
                status="queued",
                available_at__lte=now,
                attempts__gt=0,
                attempts__lt=MAX_ATTEMPTS,
            )
            .order_by("available_at", "id")
            [:OPPORTUNISTIC_RETRY_LIMIT]
        )
        directives = list(retryable)

    for d in directives:
        _process_directive(d)


@receiver(post_save, dispatch_uid="ordering.directive_dispatch")
def on_directive_post_save(sender, instance, created, **kwargs) -> None:
    """
    Auto-dispatch newly created directives.

    Only fires for Directive model, on creation, when status is "queued".
    """
    from shopman.ordering.models import Directive

    if sender is not Directive:
        return
    if not created:
        return
    if instance.status != "queued":
        return
    # Reentrancy guard: don't cascade when a handler creates child directives.
    if getattr(_local, "dispatching", False):
        return

    _process_directive(instance)
    _retry_failed_directives(instance.topic)
