"""
Signal-driven directive dispatch with transaction safety.

Processes newly created directives via post_save signal, but defers actual
processing to transaction.on_commit() so that side effects (notifications,
payment calls, etc.) only occur after the database transaction commits.

The process_directives --watch command remains as fallback for edge cases
(worker crash, deploy gap, etc.) but is not required for normal operation.
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
# Those child directives stay "queued" and are picked up by the poller or
# the next signal-driven dispatch.
_local = threading.local()


def _backoff_seconds(attempts: int) -> int:
    """Exponential backoff: 2^attempts seconds."""
    return 2 ** attempts


def _process_directive(directive) -> None:
    """
    Process a single directive using its registered handler.

    On success: marks as "done" (handler is responsible for setting status).
    On failure: marks as "queued" with backoff, or "failed" if max attempts reached.

    Sets a thread-local reentrancy flag so that directives created by the
    handler itself are not auto-dispatched (avoids cascading side-effects).
    """
    from shopman.orderman import registry

    handler = registry.get_directive_handler(directive.topic)
    if not handler:
        logger.warning("No handler registered for topic %s, leaving queued.", directive.topic)
        return

    now = timezone.now()
    directive.status = "running"
    directive.attempts += 1
    directive.started_at = now
    directive.save(update_fields=["status", "attempts", "started_at", "updated_at"])

    from shopman.orderman.exceptions import DirectiveTerminalError, DirectiveTransientError

    _local.dispatching = True
    try:
        handler.handle(message=directive, ctx={"actor": "signal_dispatch"})
        # Auto-complete: only if handler didn't change status (e.g. deferral)
        directive.refresh_from_db()
        if directive.status == "running":
            directive.status = "done"
            directive.save(update_fields=["status", "updated_at"])
    except DirectiveTerminalError as exc:
        logger.error(
            "Directive %s #%s terminal failure (attempt %d): %s",
            directive.topic, directive.pk, directive.attempts, exc,
        )
        directive.status = "failed"
        directive.error_code = "terminal"
        directive.last_error = str(exc)[:500]
        directive.save(update_fields=["status", "error_code", "last_error", "updated_at"])
    except DirectiveTransientError as exc:
        logger.warning(
            "Directive %s #%s transient failure (attempt %d/%d): %s",
            directive.topic, directive.pk, directive.attempts, MAX_ATTEMPTS, exc,
        )
        if directive.attempts >= MAX_ATTEMPTS:
            directive.status = "failed"
            directive.error_code = "terminal"
        else:
            directive.status = "queued"
            directive.error_code = "transient"
            directive.available_at = now + timedelta(seconds=_backoff_seconds(directive.attempts))
        directive.last_error = str(exc)[:500]
        directive.save(update_fields=["status", "error_code", "available_at", "last_error", "updated_at"])
    except Exception as exc:
        logger.exception(
            "Directive %s #%s failed (attempt %d/%d)",
            directive.topic, directive.pk, directive.attempts, MAX_ATTEMPTS,
        )
        if directive.attempts >= MAX_ATTEMPTS:
            directive.status = "failed"
            directive.error_code = "terminal"
        else:
            directive.status = "queued"
            directive.error_code = "transient"
            directive.available_at = now + timedelta(seconds=_backoff_seconds(directive.attempts))
        directive.last_error = str(exc)[:500]
        directive.save(update_fields=["status", "error_code", "available_at", "last_error", "updated_at"])
    finally:
        _local.dispatching = False


def _retry_failed_directives(topic: str) -> None:
    """
    Opportunistic retry: sweep up to OPPORTUNISTIC_RETRY_LIMIT failed/queued
    directives for the same topic whose available_at has passed.
    """
    from shopman.orderman.models import Directive

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


def _on_commit_callback(directive_pk: int, topic: str) -> None:
    """
    Callback executed after the transaction commits.

    Re-fetches the directive by pk to get fresh post-commit state.
    Skips processing if the directive no longer exists or is not "queued"
    (e.g., rolled back or already processed by another worker).
    """
    from shopman.orderman.models import Directive

    try:
        directive = Directive.objects.get(pk=directive_pk)
    except Directive.DoesNotExist:
        logger.debug("Directive #%s not found post-commit (rolled back?), skipping.", directive_pk)
        return

    if directive.status != "queued":
        logger.debug(
            "Directive #%s status is %s post-commit, skipping.",
            directive_pk, directive.status,
        )
        return

    _process_directive(directive)
    _retry_failed_directives(topic)


@receiver(post_save, dispatch_uid="orderman.directive_dispatch")
def on_directive_post_save(sender, instance, created, **kwargs) -> None:
    """
    Auto-dispatch newly created directives after transaction commit.

    Only fires for Directive model, on creation, when status is "queued".
    Defers processing to transaction.on_commit() so side effects only occur
    after the database transaction commits successfully.
    """
    from shopman.orderman.models import Directive

    if sender is not Directive:
        return
    if not created:
        return
    if instance.status != "queued":
        return
    # Reentrancy guard: don't cascade when a handler creates child directives.
    if getattr(_local, "dispatching", False):
        return

    transaction.on_commit(lambda: _on_commit_callback(instance.pk, instance.topic))
