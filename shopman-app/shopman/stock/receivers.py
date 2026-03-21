"""
Signal receivers for stock events.

Listens to Stockman's holds_materialized signal to auto-commit
sessions that were waiting for production to complete.
"""

from __future__ import annotations

import logging
import uuid

from django.db import transaction

logger = logging.getLogger(__name__)


def _stockman_available() -> bool:
    try:
        from shopman.stocking.signals import holds_materialized  # noqa: F401
        return True
    except ImportError:
        return False


def connect_signals():
    """
    Connect signal receivers. Called from StockConfig.ready().
    """
    if not _stockman_available():
        logger.debug("Stockman not installed, skipping holds_materialized receiver.")
        return

    from shopman.stocking.signals import holds_materialized

    holds_materialized.connect(_on_holds_materialized)
    logger.info("Connected holds_materialized receiver.")


def _on_holds_materialized(sender, hold_ids, sku, target_date, **kwargs):
    """
    React when planned holds are materialized (stock became physical).
    """
    if not hold_ids:
        return

    from shopman.stocking.models import Hold

    # Collect unique session_keys from materialized holds
    session_keys = set()
    for hold_id in hold_ids:
        try:
            pk = int(hold_id.split(":")[1])
            hold = Hold.objects.get(pk=pk)
            ref = (hold.metadata or {}).get("reference")
            if ref:
                session_keys.add(ref)
        except (Hold.DoesNotExist, IndexError, ValueError, TypeError):
            logger.debug("Could not resolve hold %s to session_key", hold_id)

    if not session_keys:
        logger.debug(
            "holds_materialized: no session_keys found for holds %s",
            hold_ids,
        )
        return

    from shopman.ordering.models import Session

    sessions = Session.objects.filter(
        session_key__in=session_keys,
        state="open",
    ).select_related("channel")

    for session in sessions:
        check_result = (
            (session.data or {})
            .get("checks", {})
            .get("stock", {})
            .get("result", {})
        )
        if not check_result.get("has_planned_holds"):
            continue

        if not _all_holds_materialized(check_result):
            logger.info(
                "Session %s:%s still has planned holds, skipping auto-commit",
                session.channel.ref, session.session_key,
            )
            continue

        try:
            _auto_commit_session(session)
        except Exception:
            logger.warning(
                "Failed to auto-commit session %s:%s after stock materialization",
                session.channel.ref, session.session_key,
                exc_info=True,
            )


def _all_holds_materialized(check_result: dict) -> bool:
    """Check if all planned holds now have physical stock."""
    from shopman.stocking.models import Hold

    planned_holds = [h for h in check_result.get("holds", []) if h.get("is_planned")]
    if not planned_holds:
        return True

    for hold_data in planned_holds:
        hold_id = hold_data.get("hold_id")
        if not hold_id:
            continue
        try:
            pk = int(hold_id.split(":")[1])
            hold = Hold.objects.get(pk=pk)
            if hold.quant is None or hold.quant.target_date is not None:
                return False
        except (Hold.DoesNotExist, IndexError, ValueError):
            return False

    return True


def _auto_commit_session(session):
    """
    Auto-commit a session after stock materialization.
    """
    from shopman.ordering.services.commit import CommitService

    idempotency_key = f"auto-commit-{session.session_key}-{uuid.uuid4().hex[:8]}"

    logger.info(
        "Auto-committing session %s:%s (stock materialized)",
        session.channel.ref, session.session_key,
    )

    result = CommitService.commit(
        session_key=session.session_key,
        channel_ref=session.channel.ref,
        idempotency_key=idempotency_key,
        ctx={"actor": "stock_materialized"},
    )

    logger.info(
        "Auto-commit successful: session=%s:%s order=%s",
        session.channel.ref, session.session_key,
        result.get("order_ref"),
    )
